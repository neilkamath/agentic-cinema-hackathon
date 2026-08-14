import anyio
from fastapi import FastAPI

from agent import rank_comments
from youtube import fetch_comments

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    comments = await anyio.to_thread.run_sync(fetch_comments, video_id)
    ranked = await rank_comments(comments)
    return {"video_id": video_id, "comments": ranked}
