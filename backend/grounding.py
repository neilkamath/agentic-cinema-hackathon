import asyncio
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

_VERDICT_PROMPT = """You fact-check YouTube comments against web search evidence. For each comment below, decide whether its claim is confirmed or disputed by the evidence, and cite the single best supporting source.

- status: "confirmed" if the evidence supports the claim, "disputed" if it contradicts or fails to support it.
- excerpt: a short quote (under 200 characters) from the evidence backing your verdict, suitable to show on hover.
- url: the source URL the excerpt came from.

{items}

Return a JSON array with exactly one object per comment id above, each with fields: id, status, excerpt, url."""


class _Verdict(BaseModel):
    id: str
    status: Literal["confirmed", "disputed"]
    excerpt: str
    url: str


_verdict_list_adapter = TypeAdapter(list[_Verdict])


async def _search(comment: dict):
    result = await _parallel.search(
        objective=comment["search_objective"],
        search_queries=comment["search_queries"],
        mode=_SEARCH_MODE,
        max_chars_total=_MAX_CHARS_PER_SEARCH,
    )
    return comment, result


def _format_item(comment, result) -> str:
    sources = "\n".join(
        f"  - {r.url} ({r.title or 'untitled'}): {' '.join(r.excerpts)}"
        for r in result.results
    ) or "  (no search results found)"
    return (
        f'Comment {comment["id"]}: "{comment["text"]}"\n'
        f'Claim to check: {comment["search_objective"]}\n'
        f"Evidence:\n{sources}"
    )


async def ground_comments(flagged: list[dict]) -> dict[str, dict]:
    if not flagged:
        return {}

    searched = await asyncio.gather(*(_search(c) for c in flagged))
    items = "\n\n".join(_format_item(c, r) for c, r in searched)

    resp = await _gemini.aio.models.generate_content(
        model=_MODEL,
        contents=_VERDICT_PROMPT.format(items=items),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_Verdict],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    verdicts = {v.id: v for v in _verdict_list_adapter.validate_json(resp.text)}

    return {
        cid: {"status": v.status, "excerpt": v.excerpt, "url": v.url}
        for cid, v in verdicts.items()
    }
