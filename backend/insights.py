import asyncio
import math
import os
from typing import Literal

from google import genai
from google.genai import types
from parallel import AsyncParallel
from pydantic import BaseModel, TypeAdapter

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
_CHUNK_BATCH_SIZE = 4

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
_SCAN_PROMPT = """Below is a short excerpt from a video's transcript (title: "{title}"), given as numbered, timestamped chunks. Identify any genuinely interesting real-world facts or topics actually mentioned in THIS excerpt that a curious viewer would want to learn more about - the kind of "did you know" moment worth surfacing. Only use what's actually said here - if nothing in this excerpt is genuinely interesting, return an empty array. For each one you find, give:
- topic: a short description of the fact/topic
- category (one of: {categories})
- video_reference: one short sentence paraphrasing what's actually said here that inspired this topic - name who said it if it's clear from context (e.g. "Jon mentioned he played catcher for a baseball team in Russia")
- chunk_index: the number of the exact chunk below where this is discussed (must be one of the chunk numbers shown below)

Transcript excerpt:
{transcript}

Return a JSON array (can be empty) of objects with fields: topic, category, video_reference, chunk_index."""

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


class _Topic(BaseModel):
    topic: str
    search_objective: str
    search_queries: list[str]
    category: Literal["background", "did_you_know", "deeper_dive", "related_event"]
    video_reference: str | None = None
    chunk_index: int | None = None


class _Candidate(BaseModel):
    topic: str
    category: Literal["background", "did_you_know", "deeper_dive", "related_event"]
    video_reference: str
    chunk_index: int


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


_topic_list_adapter = TypeAdapter(list[_Topic])
_candidate_list_adapter = TypeAdapter(list[_Candidate])
_selection_list_adapter = TypeAdapter(list[_Selection])
_insight_list_adapter = TypeAdapter(list[_Insight])


def _fmt_time(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _format_transcript(transcript_chunks: list[dict]) -> str:
    return "\n".join(f"[{_fmt_time(c['start_seconds'])}] {c['text']}" for c in transcript_chunks)


def _format_chunk_batch(batch: list[tuple[int, dict]]) -> str:
    return "\n".join(f"[{i}] [{_fmt_time(c['start_seconds'])}] {c['text']}" for i, c in batch)


async def _scan_batch(title: str, batch: list[tuple[int, dict]]) -> list[_Candidate]:
    valid_indices = {i for i, _ in batch}
    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_SCAN_PROMPT.format(
            title=title,
            categories=", ".join(_CATEGORIES),
            transcript=_format_chunk_batch(batch),
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Candidate],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    candidates = _candidate_list_adapter.validate_json(resp.text)
    # Defensive: the model only ever saw these chunks, so drop anything that
    # claims an index it wasn't actually shown.
    return [c for c in candidates if c.chunk_index in valid_indices]


async def _scan_transcript_for_candidates(title: str, transcript_chunks: list[dict]) -> list[_Candidate]:
    indexed = list(enumerate(transcript_chunks))
    batches = [indexed[i : i + _CHUNK_BATCH_SIZE] for i in range(0, len(indexed), _CHUNK_BATCH_SIZE)]
    results = await asyncio.gather(*(_scan_batch(title, batch) for batch in batches))
    return [candidate for batch_result in results for candidate in batch_result]


async def _select_topics(candidates: list[_Candidate], num_chunks: int) -> list[_Topic]:
    candidates_by_id = {f"c{i}": c for i, c in enumerate(candidates)}

    # Bucket by chunk_index into _NUM_INSIGHTS equal segments spanning the
    # video's full chunk range, so segment membership is deterministic - the
    # model only has to judge quality within each segment, not police its own
    # spread across the video.
    bucket_size = max(1, math.ceil(num_chunks / _NUM_INSIGHTS))
    buckets: list[list[tuple[str, _Candidate]]] = [[] for _ in range(_NUM_INSIGHTS)]
    for cid, c in candidates_by_id.items():
        bucket_idx = min(_NUM_INSIGHTS - 1, c.chunk_index // bucket_size)
        buckets[bucket_idx].append((cid, c))

    segments = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        lines = "\n".join(
            f"  [{cid}] topic: {c.topic} | category: {c.category} | reference: {c.video_reference}"
            for cid, c in bucket
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
        candidate = candidates_by_id.get(sel.candidate_id)
        if candidate is None:
            continue
        topics.append(
            _Topic(
                topic=candidate.topic,
                search_objective=sel.search_objective,
                search_queries=sel.search_queries,
                category=candidate.category,
                video_reference=candidate.video_reference,
                chunk_index=candidate.chunk_index,
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
        candidates = await _scan_transcript_for_candidates(title, transcript_chunks)
        return await _select_topics(candidates, len(transcript_chunks)) if candidates else []

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
            response_schema=list[_Topic],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return _topic_list_adapter.validate_json(topic_resp.text)


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
    topics_by_name = {t.topic: t for t in topics}

    def resolve_timestamp(topic: "_Topic | None") -> float | None:
        # The chunk_index always comes from a chunk the model actually scanned
        # in isolation (Stage A), and the real timestamp always comes from our
        # own chunk data - never from a value the model wrote itself - so an
        # out-of-range or invented timestamp is impossible.
        if topic is None or topic.chunk_index is None or transcript_chunks is None:
            return None
        if not (0 <= topic.chunk_index < len(transcript_chunks)):
            return None
        return transcript_chunks[topic.chunk_index]["start_seconds"]

    insights = []
    for i, w in enumerate(written):
        topic = topics_by_name.get(w.topic)
        insights.append(
            {
                "id": f"insight-{i}",
                "category": topic.category if topic else "did_you_know",
                "headline": w.headline,
                "video_reference": topic.video_reference if topic else None,
                "text": w.text,
                "source_url": w.url,
                "topic": w.topic,
                "timestamp_seconds": resolve_timestamp(topic),
            }
        )

    return {"summary": summary, "insights": insights}
