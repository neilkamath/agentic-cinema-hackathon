import anyio
from fastapi import FastAPI

from agent import rank_comments
from grounding import ground_comments
from youtube import fetch_comments

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    comments = await anyio.to_thread.run_sync(fetch_comments, video_id)
    ranked = await rank_comments(comments)
    flagged = [c for c in ranked if c["needs_grounding"]]
    groundings = await ground_comments(flagged)
    comments_out = [
        {
            **{k: v for k, v in c.items() if k not in ("search_objective", "search_queries")},
            "grounding_status": groundings.get(c["id"], {}).get("status"),
            "grounding_excerpt": groundings.get(c["id"], {}).get("excerpt"),
            "grounding_url": groundings.get(c["id"], {}).get("url"),
        }
        for c in ranked
    ]
    return {"video_id": video_id, "comments": comments_out}
