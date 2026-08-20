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
