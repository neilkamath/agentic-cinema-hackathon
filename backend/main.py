from dotenv import load_dotenv

# Must run before the env-reading imports below - local dev sources secrets
# from this file, and it needs to be loaded in-process (not just exported in
# the launching shell) so uvicorn's --reload respawns still see it.
load_dotenv()

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from insights import generate_insights
from transcript import chunk_transcript, fetch_transcript
from youtube import fetch_comments, fetch_comments_since, fetch_video_metadata

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class PollRequest(BaseModel):
    after: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    comments = await anyio.to_thread.run_sync(fetch_comments, video_id)
    cursor = max((c["published_at"] for c in comments), default=None)
    return {"video_id": video_id, "comments": comments, "cursor": cursor}


@app.post("/comments/{video_id}/poll")
async def poll_comments(video_id: str, body: PollRequest):
    new_comments = await anyio.to_thread.run_sync(fetch_comments_since, video_id, body.after)
    if not new_comments:
        return {"comments": [], "cursor": body.after}

    cursor = max(c["published_at"] for c in new_comments)
    return {"comments": new_comments, "cursor": cursor}


@app.get("/video/{video_id}/insights")
async def get_insights(video_id: str):
    metadata = await anyio.to_thread.run_sync(fetch_video_metadata, video_id)
    segments = await anyio.to_thread.run_sync(fetch_transcript, video_id)
    transcript_chunks = chunk_transcript(segments) if segments else None
    result = await generate_insights(metadata["title"], metadata["description"], transcript_chunks)
    return {
        "video_id": video_id,
        "title": metadata["title"],
        "channel_title": metadata["channel_title"],
        "summary": result["summary"],
        "insights": result["insights"],
    }
