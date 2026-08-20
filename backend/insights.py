import asyncio
import logging
import math
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from google import genai
from google.genai import types
from parallel import AsyncParallel
from pydantic import BaseModel, TypeAdapter

_log = logging.getLogger(__name__)

_gemini = genai.Client(
    vertexai=True,
    project=os.environ["GCP_PROJECT"],
    location=os.environ["GCP_LOCATION"],
)
_parallel = AsyncParallel(api_key=os.environ["PARALLEL_API_KEY"])
_MODEL = "gemini-2.5-flash"
_SEARCH_MODE = "fast"
_MAX_CHARS_PER_SEARCH = 3000
_NUM_INSIGHTS = 5
_MAX_DESCRIPTION_CHARS = 2000
_CHUNK_BATCH_SIZE = 6
# Fraction of a quote that must be found contiguously in the transcript for
# the candidate to count as genuinely sourced from it.
_MIN_QUOTE_MATCH = 0.6

_CATEGORIES = ["background", "did_you_know", "deeper_dive", "related_event"]

_TOPIC_PROMPT = """Given this video's title and description, identify {n} distinct, genuinely interesting real-world facts or topics related to its subject matter that a curious viewer would want to learn more about - the kind of "did you know" insight worth surfacing while watching. For each, give a self-contained search objective, 2-3 search queries to find grounding evidence, and a category (one of: {categories}).

Title: {title}
Description: {description}

Return a JSON array of exactly {n} objects, each with fields: topic, search_objective, search_queries, category."""

# Scans one small excerpt of the transcript in isolation (Stage A) - the
# model has nothing else in front of it, so whatever it finds is guaranteed
# to actually be in this excerpt. This replaces asking the model to read the
# entire transcript and recall where a topic came from afterward, which is
# an unreliable long-context retrieval task (verified: ~20-40% placement
# accuracy on conversational content, even with a larger thinking budget).
# The verbatim quote is the real placement anchor: the timestamp is derived
# server-side by string-matching the quote against the transcript, so the
# model's chunk_index is only a hint and an unfindable quote disqualifies
# the candidate.
_SCAN_PROMPT = """Below is a short excerpt from a video's transcript (title: "{title}"), given as numbered, timestamped chunks. Identify any genuinely interesting real-world facts or topics actually mentioned in THIS excerpt that a curious viewer would want to learn more about - the kind of "did you know" moment worth surfacing. Only use what's actually said here - if nothing in this excerpt is genuinely interesting, return an empty array. For each one you find, give:
- topic: a short description of the fact/topic
- category (one of: {categories})
- video_reference: one short sentence paraphrasing what's actually said here that inspired this topic - name who said it if it's clear from context (e.g. "Jon mentioned he played catcher for a baseball team in Russia")
- quote: a short span (roughly 5-15 words) copied VERBATIM from the chunk where this is discussed - the exact words as they appear, not paraphrased, cleaned up, or stitched together from different places
- chunk_index: the number of the exact chunk below where this is discussed (must be one of the chunk numbers shown below)

The excerpt may begin with an unnumbered chunk marked "context only" - use it to follow the conversation, but never take quotes or chunk numbers from it.

Transcript excerpt:
{transcript}

Return a JSON array (can be empty) of objects with fields: topic, category, video_reference, quote, chunk_index."""

# Picks one candidate from each video segment (Stage B) and writes search
# queries for them. Candidates are grouped into segments (rather than left as
# one flat list) so the final picks are structurally spread across the whole
# video - a flat "pick the best {n} from this list" call showed a strong bias
# toward candidates appearing later in the list (and therefore later in the
# video), even though the candidate pool itself was well distributed.
_SELECT_PROMPT = """The candidates below are grouped by which part of the video they come from (Segment 1 is earliest, later segments are later in the video). From EACH segment listed, pick the single most genuinely interesting candidate. For each one you pick, also write a self-contained search objective and 2-3 search queries to find grounding evidence about it.

{segments}

Return a JSON array with exactly one object per segment above, each with fields: candidate_id, search_objective, search_queries."""

_INSIGHT_PROMPT = """For each topic below, write:
- headline: a short, punchy, attention-grabbing phrase (3-6 words, not a full sentence) that hooks the reader
- text: the fact itself, grounded in the evidence provided - exactly ONE short, easy-to-read sentence, no more than 20 words, no filler
- url: its single best source

{items}

Return a JSON array with one object per topic above, each with fields: topic, headline, text, url."""

_SUMMARY_PROMPT = """Write a spoiler-free, 2-3 sentence summary of what this video is about, based on its title and description{transcript_note}. Describe the topic and premise only - do NOT reveal outcomes, twists, results, punchlines, or conclusions.

Title: {title}
Description: {description}
{transcript_block}
Return a JSON object with a single field: summary."""


_Category = Literal["background", "did_you_know", "deeper_dive", "related_event"]


# Response schema for the no-transcript path only - it must not contain
# timestamp or placement fields, so the model never gets a slot to write one.
class _GeneratedTopic(BaseModel):
    topic: str
    search_objective: str
    search_queries: list[str]
    category: _Category


# Internal only, never a Gemini response schema: timestamp_seconds is always
# computed server-side from the transcript, never model-written.
class _Topic(BaseModel):
    topic: str
    search_objective: str
    search_queries: list[str]
    category: _Category
    video_reference: str | None = None
    quote: str | None = None
    timestamp_seconds: float | None = None


class _Candidate(BaseModel):
    topic: str
    category: _Category
    video_reference: str
    quote: str
    chunk_index: int


# A candidate whose quote was actually found in the transcript, with the
# chunk index corrected to where the quote really is and the timestamp of
# the exact segment containing it.
@dataclass
class _ScanHit:
    candidate: _Candidate
    chunk_index: int
    timestamp_seconds: float


class _Selection(BaseModel):
    candidate_id: str
    search_objective: str
    search_queries: list[str]


class _Insight(BaseModel):
    topic: str
    headline: str
    text: str
    url: str


class _Summary(BaseModel):
    summary: str


_generated_topic_list_adapter = TypeAdapter(list[_GeneratedTopic])
_candidate_list_adapter = TypeAdapter(list[_Candidate])
_selection_list_adapter = TypeAdapter(list[_Selection])
_insight_list_adapter = TypeAdapter(list[_Insight])


def _fmt_time(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _format_transcript(transcript_chunks: list[dict]) -> str:
    return "\n".join(f"[{_fmt_time(c['start_seconds'])}] {c['text']}" for c in transcript_chunks)


def _format_chunk_batch(batch: list[tuple[int, dict]], context_chunk: dict | None) -> str:
    lines = []
    if context_chunk is not None:
        lines.append(
            f"(context only) [{_fmt_time(context_chunk['start_seconds'])}] {context_chunk['text']}"
        )
    lines.extend(f"[{i}] [{_fmt_time(c['start_seconds'])}] {c['text']}" for i, c in batch)
    return "\n".join(lines)


def _normalize(text: str) -> str:
    # Bracketed spans are ASR annotations - "(upbeat music)", "[ __ ]",
    # "[Narrator]" - that get interleaved mid-sentence and would break an
    # otherwise contiguous match against a verbatim quote.
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _resolve_candidate(candidate: _Candidate, batch: list[tuple[int, dict]]) -> _ScanHit | None:
    # Placement is decided by string-matching the model's verbatim quote
    # against our own transcript text - the model's chunk_index only breaks
    # ties when the same words occur more than once. The whole batch is
    # searched as one haystack so quotes spanning a chunk boundary still
    # match. A quote that can't be found anywhere in the batch means the
    # topic wasn't genuinely read off the transcript, so it's dropped.
    nquote = _normalize(candidate.quote)
    if not nquote:
        return None

    parts = []
    spans = []  # (end offset of this segment in the haystack, chunk index, start time)
    pos = 0
    for index, chunk in batch:
        for seg in chunk.get("segments") or [chunk]:
            ntext = _normalize(seg["text"])
            if not ntext:
                continue
            parts.append(ntext)
            spans.append((pos + len(ntext), index, seg["start_seconds"]))
            pos += len(ntext) + 1
    if not spans:
        return None
    haystack = " ".join(parts)

    def span_at(offset: int) -> tuple[int, float]:
        for end, index, start_seconds in spans:
            if offset < end:
                return index, start_seconds
        return spans[-1][1], spans[-1][2]

    occurrences = []
    found = haystack.find(nquote)
    while found >= 0:
        occurrences.append(found)
        found = haystack.find(nquote, found + 1)
    if occurrences:
        offset = next(
            (o for o in occurrences if span_at(o)[0] == candidate.chunk_index), occurrences[0]
        )
    else:
        m = SequenceMatcher(None, nquote, haystack, autojunk=False).find_longest_match(
            0, len(nquote), 0, len(haystack)
        )
        if m.size < _MIN_QUOTE_MATCH * len(nquote):
            return None
        offset = max(0, m.b - m.a)

    index, timestamp = span_at(offset)
    return _ScanHit(candidate=candidate, chunk_index=index, timestamp_seconds=timestamp)


async def _scan_batch(
    title: str, batch: list[tuple[int, dict]], context: tuple[int, dict] | None
) -> list[_ScanHit]:
    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_SCAN_PROMPT.format(
            title=title,
            categories=", ".join(_CATEGORIES),
            transcript=_format_chunk_batch(batch, context[1] if context else None),
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Candidate],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    candidates = _candidate_list_adapter.validate_json(resp.text)
    # The context chunk joins the searchable text so a quote straddling the
    # batch boundary still resolves - quote matching makes citing it safe,
    # since placement is verified against the transcript either way.
    searchable = ([context] if context else []) + batch
    hits = []
    for candidate in candidates:
        hit = _resolve_candidate(candidate, searchable)
        if hit is None:
            _log.info("dropping candidate with unlocatable quote: %r", candidate.quote)
            continue
        hits.append(hit)
    return hits


async def _scan_transcript_for_candidates(title: str, transcript_chunks: list[dict]) -> list[_ScanHit]:
    indexed = list(enumerate(transcript_chunks))
    tasks = []
    for i in range(0, len(indexed), _CHUNK_BATCH_SIZE):
        batch = indexed[i : i + _CHUNK_BATCH_SIZE]
        # The previous chunk rides along unnumbered so conversational threads
        # that straddle a batch boundary can still be followed; the model
        # can't cite it, but the resolver can still anchor a quote in it.
        context = indexed[i - 1] if i > 0 else None
        tasks.append(_scan_batch(title, batch, context))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    hits = []
    for result in results:
        if isinstance(result, BaseException):
            _log.warning("transcript scan batch failed, skipping it: %s", result)
            continue
        hits.extend(result)
    return hits


async def _select_topics(hits: list[_ScanHit], num_chunks: int) -> list[_Topic]:
    hits_by_id = {f"c{i}": h for i, h in enumerate(hits)}

    # Bucket by chunk_index into _NUM_INSIGHTS equal segments spanning the
    # video's full chunk range, so segment membership is deterministic - the
    # model only has to judge quality within each segment, not police its own
    # spread across the video.
    bucket_size = max(1, math.ceil(num_chunks / _NUM_INSIGHTS))
    buckets: list[list[tuple[str, _ScanHit]]] = [[] for _ in range(_NUM_INSIGHTS)]
    for cid, h in hits_by_id.items():
        bucket_idx = min(_NUM_INSIGHTS - 1, h.chunk_index // bucket_size)
        buckets[bucket_idx].append((cid, h))

    segments = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        lines = "\n".join(
            f"  [{cid}] topic: {h.candidate.topic} | category: {h.candidate.category}"
            f" | reference: {h.candidate.video_reference}"
            for cid, h in bucket
        )
        segments.append(f"Segment {i + 1}:\n{lines}")

    if not segments:
        return []

    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_SELECT_PROMPT.format(segments="\n\n".join(segments)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Selection],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    selections = _selection_list_adapter.validate_json(resp.text)

    topics = []
    for sel in selections:
        hit = hits_by_id.get(sel.candidate_id)
        if hit is None:
            continue
        topics.append(
            _Topic(
                topic=hit.candidate.topic,
                search_objective=sel.search_objective,
                search_queries=sel.search_queries,
                category=hit.candidate.category,
                video_reference=hit.candidate.video_reference,
                quote=hit.candidate.quote,
                timestamp_seconds=hit.timestamp_seconds,
            )
        )
    return topics


async def _search_topic(topic: _Topic):
    result = await _parallel.search(
        objective=topic.search_objective,
        search_queries=topic.search_queries,
        mode=_SEARCH_MODE,
        max_chars_total=_MAX_CHARS_PER_SEARCH,
    )
    return topic, result


def _format_item(topic: _Topic, result) -> str:
    sources = "\n".join(
        f"  - {r.url} ({r.title or 'untitled'}): {' '.join(r.excerpts)}" for r in result.results
    ) or "  (no search results found)"
    return f"Topic: {topic.topic}\nObjective: {topic.search_objective}\nEvidence:\n{sources}"


async def _generate_summary(title: str, description: str, transcript_chunks: list[dict] | None) -> str:
    transcript_note = " and transcript" if transcript_chunks else ""
    transcript_block = f"\nTranscript excerpt:\n{_format_transcript(transcript_chunks)}\n" if transcript_chunks else ""
    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_SUMMARY_PROMPT.format(
            title=title,
            description=description[:_MAX_DESCRIPTION_CHARS],
            transcript_note=transcript_note,
            transcript_block=transcript_block,
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_Summary,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return _Summary.model_validate_json(resp.text).summary


async def _generate_topics(title: str, description: str, transcript_chunks: list[dict] | None) -> list[_Topic]:
    if transcript_chunks:
        hits = await _scan_transcript_for_candidates(title, transcript_chunks)
        return await _select_topics(hits, len(transcript_chunks)) if hits else []

    topic_resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_TOPIC_PROMPT.format(
            n=_NUM_INSIGHTS,
            title=title,
            description=description[:_MAX_DESCRIPTION_CHARS],
            categories=", ".join(_CATEGORIES),
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_GeneratedTopic],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    generated = _generated_topic_list_adapter.validate_json(topic_resp.text)
    return [_Topic(**g.model_dump()) for g in generated]


async def generate_insights(
    title: str, description: str, transcript_chunks: list[dict] | None = None
) -> dict:
    topics = await _generate_topics(title, description, transcript_chunks)
    if not topics:
        summary = await _generate_summary(title, description, transcript_chunks)
        return {"summary": summary, "insights": []}

    # Summary generation doesn't depend on the searches, so run it alongside
    # them instead of after - costs no extra latency.
    searched, summary = await asyncio.gather(
        asyncio.gather(*(_search_topic(t) for t in topics)),
        _generate_summary(title, description, transcript_chunks),
    )
    items = "\n\n".join(_format_item(t, r) for t, r in searched)

    insight_resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_INSIGHT_PROMPT.format(items=items),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Insight],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    written = _insight_list_adapter.validate_json(insight_resp.text)

    insights = []
    for i, w in enumerate(written):
        # The writing stage echoes topics back in input order, so position -
        # not the echoed topic string, which the model sometimes rewrites - is
        # what links an insight back to its topic and timestamp. The timestamp
        # itself was derived from the transcript in Stage A and is never a
        # value the model wrote.
        topic = topics[i] if i < len(topics) else None
        insights.append(
            {
                "id": f"insight-{i}",
                "category": topic.category if topic else "did_you_know",
                "headline": w.headline,
                "video_reference": topic.video_reference if topic else None,
                "text": w.text,
                "source_url": w.url,
                "topic": w.topic,
                "timestamp_seconds": topic.timestamp_seconds if topic else None,
            }
        )

    return {"summary": summary, "insights": insights}
