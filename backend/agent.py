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
- filter_out (true/false): true only if the comment is spam, a bot/scam/ad comment, or a near-duplicate of another comment in this same list (or of one of the already-shown comments below, if given). Otherwise false.
- needs_grounding (true/false): true only if the comment makes a specific factual claim about the video's subject matter that is independently verifiable from public sources (a fact, statistic, historical event, or quote someone else could look up and confirm or refute). False for opinions, jokes, reactions, and personal anecdotes about the commenter's own experience (e.g. "I saw this in person," "my professor told us...") - even when they mention a real-world detail, nobody can verify one person's private experience against public sources, so grounding it would be meaningless.
- search_objective: if needs_grounding is true, a self-contained one-sentence description of the specific claim to verify (include enough context to search for it standalone - the comment text alone may be ambiguous). Otherwise null.
- search_queries: if needs_grounding is true, 2-3 concise web search queries (3-6 words each) that would help verify the claim. Otherwise null.
{context_block}
Comments (tab-separated: id, author, like count, text):
{comments}

Return a JSON array with exactly one object per comment id above, each with fields: id, score, filter_out, needs_grounding, search_objective, search_queries."""

_CONTEXT_BLOCK = """
Comments already shown to the viewer, for calibration only - use these as a reference point for scoring, and treat any comment above as filter_out=true if it's a near-duplicate of one of these. Do NOT output an entry for any of these ids.
{lines}
"""


class _RankedComment(BaseModel):
    id: str
    score: int
    filter_out: bool
    needs_grounding: bool
    search_objective: str | None = None
    search_queries: list[str] | None = None


_ranked_list_adapter = TypeAdapter(list[_RankedComment])


def _format_comment_line(comment: dict) -> str:
    return (
        f"{comment['id']}\t{comment.get('author', '')}\t{comment.get('like_count', '')} likes\t"
        f"{comment['text'].replace(chr(10), ' ').replace(chr(9), ' ')}"
    )


async def rank_comments(comments: list[dict], context: list[dict] | None = None) -> list[dict]:
    listing = "\n".join(_format_comment_line(c) for c in comments)
    context_block = ""
    if context:
        context_lines = "\n".join(
            f"{c['id']}\t{c['score']} (already shown)\t{c['text'].replace(chr(10), ' ').replace(chr(9), ' ')}"
            for c in context
        )
        context_block = _CONTEXT_BLOCK.format(lines=context_lines)

    resp = await _client.aio.models.generate_content(
        model=_MODEL,
        contents=_PROMPT.format(comments=listing, context_block=context_block),
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
