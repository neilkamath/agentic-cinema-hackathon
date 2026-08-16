import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import rank_comments
from factcards import generate_fact_cards
from youtube import fetch_comments, fetch_comments_since, fetch_video_metadata

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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    comments = await anyio.to_thread.run_sync(fetch_comments, video_id)
    ranked = await rank_comments(comments)
    cursor = max((c["published_at"] for c in comments), default=None)
    return {"video_id": video_id, "comments": ranked, "cursor": cursor}


@app.post("/comments/{video_id}/poll")
async def poll_comments(video_id: str, body: PollRequest):
    new_comments = await anyio.to_thread.run_sync(fetch_comments_since, video_id, body.after)
    if not new_comments:
        return {"comments": [], "cursor": body.after}

    context = [item.model_dump() for item in body.top_sample]
    ranked = await rank_comments(new_comments, context=context)
    cursor = max(c["published_at"] for c in new_comments)
    return {"comments": ranked, "cursor": cursor}


@app.get("/video/{video_id}/facts")
async def get_facts(video_id: str):
    metadata = await anyio.to_thread.run_sync(fetch_video_metadata, video_id)
    facts = await generate_fact_cards(metadata["title"], metadata["description"])
    return {"video_id": video_id, "facts": facts}
