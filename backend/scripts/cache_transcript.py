"""Fetch and cache a video's transcript for the curated demo set.

YouTube's transcript CDN blocks Cloud Run's IP range, so any video used in
the hosted demo needs its transcript pre-fetched from an unblocked network
(e.g. a local machine) and committed as a static cache file. Run this
whenever a new curated demo video is added:

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
