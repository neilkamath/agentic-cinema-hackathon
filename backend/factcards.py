import asyncio
import os

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
_NUM_TOPICS = 5
_MAX_DESCRIPTION_CHARS = 2000

_TOPIC_PROMPT = """Given this video's title and description, identify {n} distinct, genuinely interesting real-world facts or topics related to its subject matter that a curious viewer would want to learn more about - the kind of "did you know" insight worth surfacing while watching. For each, give a self-contained search objective and 2-3 search queries to find grounding evidence.

Title: {title}
Description: {description}

Return a JSON array of exactly {n} objects, each with fields: topic, search_objective, search_queries."""

_FACT_PROMPT = """For each topic below, write one genuinely interesting, factual insight (1-2 sentences) grounded in the evidence provided, plus its single best source.

{items}

Return a JSON array with one object per topic above, each with fields: topic, text, url."""


class _Topic(BaseModel):
    topic: str
    search_objective: str
    search_queries: list[str]


class _FactCard(BaseModel):
    topic: str
    text: str
    url: str


_topic_list_adapter = TypeAdapter(list[_Topic])
_fact_list_adapter = TypeAdapter(list[_FactCard])


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
        f"  - {r.url} ({r.title or 'untitled'}): {' '.join(r.excerpts)}"
        for r in result.results
    ) or "  (no search results found)"
    return f"Topic: {topic.topic}\nObjective: {topic.search_objective}\nEvidence:\n{sources}"


async def generate_fact_cards(title: str, description: str) -> list[dict]:
    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_TOPIC_PROMPT.format(
            n=_NUM_TOPICS, title=title, description=description[:_MAX_DESCRIPTION_CHARS]
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Topic],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    topics = _topic_list_adapter.validate_json(resp.text)
    if not topics:
        return []

    searched = await asyncio.gather(*(_search_topic(t) for t in topics))
    items = "\n\n".join(_format_item(t, r) for t, r in searched)

    resp2 = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_FACT_PROMPT.format(items=items),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_FactCard],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    facts = _fact_list_adapter.validate_json(resp2.text)

    return [
        {"id": f"fact-{i}", "text": f.text, "source_url": f.url, "topic": f.topic}
        for i, f in enumerate(facts)
    ]
