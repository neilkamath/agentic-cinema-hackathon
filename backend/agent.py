import os

from google import genai
from google.genai import types
from pydantic import BaseModel, TypeAdapter

_client = genai.Client(
    vertexai=True,
    project=os.environ["GCP_PROJECT"],
    location=os.environ["GCP_LOCATION"],
)
_MODEL = "gemini-2.5-flash"

_PROMPT = """You are curating the comment section of a YouTube video. Given the comments below, evaluate each one.

For every comment, decide:
- score (0-100): how insightful, thoughtful, funny, or otherwise valuable the comment is to someone reading the comments. Low-effort but genuine reactions ("great video!") should score low, not be filtered out.
- filter_out (true/false): true only if the comment is spam, a bot/scam/ad comment, or a near-duplicate of another comment in this same list. Otherwise false.
- needs_grounding (true/false): true only if the comment makes a specific, checkable factual claim about the real world (a fact, event, date, or quote that could be verified). False for opinions, jokes, or reactions.
- search_objective: if needs_grounding is true, a self-contained one-sentence description of the specific claim to verify (include enough context to search for it standalone - the comment text alone may be ambiguous). Otherwise null.
- search_queries: if needs_grounding is true, 2-3 concise web search queries (3-6 words each) that would help verify the claim. Otherwise null.

Comments (tab-separated: id, author, like count, text):
{comments}

Return a JSON array with exactly one object per comment id above, each with fields: id, score, filter_out, needs_grounding, search_objective, search_queries."""


class _RankedComment(BaseModel):
    id: str
    score: int
    filter_out: bool
    needs_grounding: bool
    search_objective: str | None = None
    search_queries: list[str] | None = None


_ranked_list_adapter = TypeAdapter(list[_RankedComment])


async def rank_comments(comments: list[dict]) -> list[dict]:
    listing = "\n".join(
        f"{c['id']}\t{c['author']}\t{c['like_count']} likes\t"
        f"{c['text'].replace(chr(10), ' ').replace(chr(9), ' ')}"
        for c in comments
    )
    resp = await _client.aio.models.generate_content(
        model=_MODEL,
        contents=_PROMPT.format(comments=listing),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[_RankedComment],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    rankings = {r.id: r for r in _ranked_list_adapter.validate_json(resp.text)}

    ranked = [
        {
            **c,
            "score": rankings[c["id"]].score,
            "needs_grounding": rankings[c["id"]].needs_grounding,
            "search_objective": rankings[c["id"]].search_objective,
            "search_queries": rankings[c["id"]].search_queries,
        }
        for c in comments
        if c["id"] in rankings and not rankings[c["id"]].filter_out
    ]
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked
