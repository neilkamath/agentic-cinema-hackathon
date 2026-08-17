import json
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

_api = YouTubeTranscriptApi()
_CACHE_DIR = Path(__file__).resolve().parent / "transcripts_cache"


def fetch_transcript(video_id: str) -> list[dict] | None:
    cached = _CACHE_DIR / f"{video_id}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    # YouTube's transcript CDN blocks Cloud Run's IP range, so this live path
    # works locally but returns None (graceful fallback) once deployed -
    # curated demo videos should be pre-fetched via scripts/cache_transcript.py.
    try:
        fetched = _api.fetch(video_id)
    except CouldNotRetrieveTranscript:
        return None
    return fetched.to_raw_data()


def chunk_transcript(segments: list[dict], chunk_seconds: float = 60) -> list[dict]:
    chunks = []
    current_start = None
    current_text: list[str] = []

    for seg in segments:
        if current_start is None:
            current_start = seg["start"]
        if seg["start"] - current_start >= chunk_seconds and current_text:
            chunks.append({"start_seconds": current_start, "text": " ".join(current_text)})
            current_start = seg["start"]
            current_text = []
        current_text.append(seg["text"])

    if current_text:
        chunks.append({"start_seconds": current_start, "text": " ".join(current_text)})

    return chunks
