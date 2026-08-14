# YT Comment Curator

A live, AI-curated comment feed for YouTube videos.

Instead of scrolling past the video to read comments, this shows them in a
scrolling side panel next to the video, like stream chat.
An agent reranks incoming comments in real time: surfacing insightful ones,
filtering spam and duplicates, and fading low-value comments rather than
hiding them.

Comments that reference a checkable claim or real-world context get grounded
against live web sources and tagged confirmed or disputed.
Comments with nothing to check are ranked on their own merits (insight,
humor, engagement) with no tag - that's expected, not a failure state.

Built for the Agentic Cinema hackathon, Parallel partner track.

## Stack

- Google Gemini (Vertex AI) for ranking and filtering
- Google Agent Development Kit (ADK) for agent orchestration
- Parallel Search API for grounding checkable claims
- YouTube Data API v3 for comment data
- Google Cloud Run for backend hosting

## Status

Early development.
See `docs/submission-checklist.md` for what's left before submission.

## Setup

Coming soon.
