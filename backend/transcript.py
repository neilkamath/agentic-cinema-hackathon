import json
import logging
import os
from pathlib import Path

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

logger = logging.getLogger(__name__)
_CACHE_DIR = Path(__file__).resolve().parent / "transcripts_cache"


def _build_proxy_config():
    # YouTube blocks transcript requests by IP reputation, and Cloud Run's
    # egress falls inside a blocked range - so the live fetch only works from
    # an unblocked (residential) IP. Locally there's no proxy configured and
    # the direct call works fine.
    username = os.getenv("WEBSHARE_PROXY_USERNAME")
    password = os.getenv("WEBSHARE_PROXY_PASSWORD")
    if username and password:
        return WebshareProxyConfig(proxy_username=username, proxy_password=password)

    proxy_url = os.getenv("TRANSCRIPT_PROXY_URL")
    if proxy_url:
        return GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)

    return None


_proxy_config = _build_proxy_config()
_api = YouTubeTranscriptApi(proxy_config=_proxy_config)


def fetch_transcript(video_id: str) -> list[dict] | None:
    cached = _CACHE_DIR / f"{video_id}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    try:
        fetched = _api.fetch(video_id)
    except (CouldNotRetrieveTranscript, requests.RequestException) as exc:
        # Logged rather than swallowed silently: an IP block, a video with
        # captions genuinely disabled, and an unreachable proxy all land here
        # and need different fixes. Caught together so a proxy outage degrades
        # to description-only insights instead of failing the whole request.
        logger.warning(
            "transcript fetch failed for %s (proxy=%s): %s",
            video_id,
            "on" if _proxy_config else "off",
            type(exc).__name__,
        )
        return None
    return fetched.to_raw_data()


def chunk_transcript(segments: list[dict], chunk_seconds: float = 60) -> list[dict]:
    # Each chunk keeps its raw segments (with per-segment start times) so a
    # quote found inside the chunk can be timestamped to the exact utterance,
    # not just the chunk boundary.
    chunks = []
    current: list[dict] = []

    def flush():
        chunks.append(
            {
                "start_seconds": current[0]["start"],
                "text": " ".join(s["text"] for s in current),
                "segments": [{"start_seconds": s["start"], "text": s["text"]} for s in current],
            }
        )

    for seg in segments:
        if current and seg["start"] - current[0]["start"] >= chunk_seconds:
            flush()
            current = []
        current.append(seg)

    if current:
        flush()

    return chunks
