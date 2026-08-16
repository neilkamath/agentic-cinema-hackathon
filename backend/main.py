import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import rank_comments
from grounding import ground_comments
from youtube import fetch_comments, fetch_comments_since

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class TopSampleItem(BaseModel):
    id: str
    text: str
    score: int


class PollRequest(BaseModel):
    after: str | None = None
    top_sample: list[TopSampleItem] = []


def _build_response_comments(ranked: list[dict], groundings: dict[str, dict]) -> list[dict]:
    return [
        {
            **{k: v for k, v in c.items() if k not in ("search_objective", "search_queries")},
            "grounding_status": groundings.get(c["id"], {}).get("status"),
            "grounding_excerpt": groundings.get(c["id"], {}).get("excerpt"),
            "grounding_url": groundings.get(c["id"], {}).get("url"),
        }
        for c in ranked
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    comments = await anyio.to_thread.run_sync(fetch_comments, video_id)
    ranked = await rank_comments(comments)
    flagged = [c for c in ranked if c["needs_grounding"]]
    groundings = await ground_comments(flagged)
    cursor = max((c["published_at"] for c in comments), default=None)
    return {
        "video_id": video_id,
        "comments": _build_response_comments(ranked, groundings),
        "cursor": cursor,
    }


@app.post("/comments/{video_id}/poll")
async def poll_comments(video_id: str, body: PollRequest):
    new_comments = await anyio.to_thread.run_sync(fetch_comments_since, video_id, body.after)
    if not new_comments:
        return {"comments": [], "cursor": body.after}

    context = [item.model_dump() for item in body.top_sample]
    ranked = await rank_comments(new_comments, context=context)
    flagged = [c for c in ranked if c["needs_grounding"]]
    groundings = await ground_comments(flagged)
    cursor = max(c["published_at"] for c in new_comments)
    return {
        "comments": _build_response_comments(ranked, groundings),
        "cursor": cursor,
    }
