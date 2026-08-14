import os

import requests

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


def fetch_comments(video_id: str, max_results: int = 100) -> list[dict]:
    resp = requests.get(
        COMMENT_THREADS_URL,
        params={
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_results,
            "order": "relevance",
            "textFormat": "plainText",
            "key": YOUTUBE_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json()["items"]
    return [
        {
            "id": item["id"],
            "author": item["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"],
            "text": item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
            "like_count": item["snippet"]["topLevelComment"]["snippet"]["likeCount"],
            "published_at": item["snippet"]["topLevelComment"]["snippet"]["publishedAt"],
        }
        for item in items
    ]
