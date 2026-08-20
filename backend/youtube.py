import os
import re

import requests

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# Matches "mm:ss" or "h:mm:ss" (e.g. "12:34" or "1:02:34"), the format
# viewers actually type when referencing a moment in the video.
_TIMESTAMP_RE = re.compile(r"\b(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)\b")


def _extract_timestamp_seconds(text: str) -> int | None:
    match = _TIMESTAMP_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = int(minutes) * 60 + int(seconds)
    if hours:
        total += int(hours) * 3600
    return total


def _parse_item(item: dict) -> dict:
    snippet = item["snippet"]["topLevelComment"]["snippet"]
    text = snippet["textDisplay"]
    return {
        "id": item["id"],
        "author": snippet["authorDisplayName"],
        "author_avatar_url": snippet["authorProfileImageUrl"],
        "text": text,
        "like_count": snippet["likeCount"],
        "published_at": snippet["publishedAt"],
        "timestamp_seconds": _extract_timestamp_seconds(text),
    }


def fetch_video_metadata(video_id: str) -> dict:
    resp = requests.get(
        VIDEOS_URL,
        params={"part": "snippet", "id": video_id, "key": YOUTUBE_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json()["items"]
    if not items:
        raise ValueError(f"video not found: {video_id}")
    snippet = items[0]["snippet"]
    return {
        "title": snippet["title"],
        "description": snippet.get("description", ""),
        "channel_title": snippet.get("channelTitle", ""),
    }


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
    return [_parse_item(item) for item in resp.json()["items"]]


def fetch_comments_since(video_id: str, after: str | None, max_pages: int = 3) -> list[dict]:
    collected = []
    page_token = None

    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
            "key": YOUTUBE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(COMMENT_THREADS_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # YouTube sometimes returns a pinned comment first regardless of `order`,
        # so a single early item can be much older than the rest of the page -
        # filter every item on value, and only use the page's last item (not its
        # first) to decide whether the boundary has been reached.
        page_comments = [_parse_item(item) for item in data["items"]]
        collected.extend(c for c in page_comments if after is None or c["published_at"] > after)

        page_token = data.get("nextPageToken")
        reached_boundary = (
            after is not None and page_comments and page_comments[-1]["published_at"] <= after
        )
        if not page_token or reached_boundary:
            break

    return collected
