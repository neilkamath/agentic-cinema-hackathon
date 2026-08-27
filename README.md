# Sidecast

A web app that plays a YouTube video next to a synced side panel.
The panel shows real YouTube comments, unranked and exactly as YouTube returns them, merged with AI-generated insight cards.
Each insight card is anchored to the real transcript moment it's grounded in, and its claim is checked against live web sources rather than asserted from model memory.

Built for the [Agentic Cinema hackathon](https://agentic-cinema.devpost.com), Parallel partner track.

## Live demo

https://sidecast.web.app

## How it works

- Comments come from the YouTube Data API v3, unranked, no algorithmic filtering.
- A Gemini agent (via Google's Agent Development Kit) scans the video's transcript in chunks to find checkable, non-obvious claims, then places them at the transcript timestamp they actually came from.
- Each claim is grounded against live web results via the Parallel Search API before being shown as an insight card.
- The side panel scrolls in sync with video playback, so comments and insight cards line up with the moment they're about.

## Stack

- `google-adk` / `google-genai` (Gemini on Vertex AI) - insight generation and placement
- `parallel-web` (Parallel Search API) - grounding
- YouTube Data API v3 - comments and video metadata
- `youtube-transcript-api` - transcript fetching
- FastAPI backend on Google Cloud Run
- Vanilla JS/HTML/CSS frontend (no build step) on Firebase Hosting

## Run locally

**Backend**

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GCP_PROJECT, YOUTUBE_API_KEY, PARALLEL_API_KEY
uvicorn main:app --reload --port 8000
```

**Frontend**

```
cd frontend
python3 -m http.server 8123
```

Then open `http://localhost:8123/index.html?api=http://localhost:8000` - the `api` param points the frontend at your local backend instead of the deployed one.

## License

MIT - see [LICENSE](LICENSE).
