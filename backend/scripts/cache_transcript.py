"""Fetch and cache a video's transcript for the curated demo set.

YouTube blocks transcript requests from Cloud Run's IP range - arbitrary
videos rely on the proxy configured in transcript.py, but the curated demo
set is committed as static cache files so it stays fast and keeps working
even if the proxy is down. Run this whenever a curated demo video is added:

    python scripts/cache_transcript.py <video_id>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transcript import fetch_transcript

CACHE_DIR = Path(__file__).resolve().parent.parent / "transcripts_cache"


def main(video_id: str) -> None:
    segments = fetch_transcript(video_id)
    if segments is None:
        print(f"No transcript available for {video_id}")
        sys.exit(1)

    CACHE_DIR.mkdir(exist_ok=True)
    out_path = CACHE_DIR / f"{video_id}.json"
    out_path.write_text(json.dumps(segments, indent=2))
    print(f"Wrote {len(segments)} segments to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/cache_transcript.py <video_id>")
        sys.exit(1)
    main(sys.argv[1])
