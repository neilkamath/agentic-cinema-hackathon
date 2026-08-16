const DEFAULT_API_BASE = "https://yt-curator-backend-659579556690.us-central1.run.app";
const API_BASE = new URLSearchParams(location.search).get("api") || DEFAULT_API_BASE;

const POLL_INTERVAL_MS = 15000;
const TOP_SAMPLE_SIZE = 15;
const SCROLL_TOP_THRESHOLD = 8;

function scoreToOpacity(score) {
  const clamped = Math.max(0, Math.min(100, score));
  return 0.35 + (clamped / 100) * 0.65;
}

function renderComment(comment) {
  const row = document.createElement("div");
  row.className = "comment";
  row.style.opacity = scoreToOpacity(comment.score);

  const header = document.createElement("div");
  header.className = "comment-header";

  const author = document.createElement("span");
  author.className = "author";
  author.textContent = comment.author;
  header.appendChild(author);

  const likes = document.createElement("span");
  likes.className = "likes";
  likes.textContent = `${comment.like_count} likes`;
  header.appendChild(likes);

  if (comment.grounding_status) {
    const badge = document.createElement("a");
    badge.className = `badge ${comment.grounding_status}`;
    badge.href = comment.grounding_url || "#";
    badge.target = "_blank";
    badge.rel = "noopener";
    badge.title = comment.grounding_excerpt || "";
    badge.textContent = comment.grounding_status === "confirmed" ? "confirmed" : "disputed";
    header.appendChild(badge);
  }

  row.appendChild(header);

  const text = document.createElement("div");
  text.className = "comment-text";
  text.textContent = comment.text;
  row.appendChild(text);

  return row;
}

export function mountPanel(container, { videoId }) {
  container.innerHTML = "";
  const list = document.createElement("div");
  list.className = "comment-list";
  container.appendChild(list);

  const state = { comments: [], cursor: null, pollTimer: null };

  const loading = document.createElement("div");
  loading.className = "loading";
  loading.textContent = "Loading comments…";
  list.appendChild(loading);

  function render() {
    const wasPinnedToTop = list.scrollTop <= SCROLL_TOP_THRESHOLD;
    const previousScrollTop = list.scrollTop;

    list.innerHTML = "";
    for (const comment of state.comments) {
      list.appendChild(renderComment(comment));
    }

    list.scrollTop = wasPinnedToTop ? 0 : previousScrollTop;
  }

  function mergeNewComments(newComments) {
    state.comments.push(...newComments);
    state.comments.sort((a, b) => b.score - a.score);
  }

  function schedulePoll() {
    state.pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }

  async function poll() {
    try {
      const topSample = state.comments.slice(0, TOP_SAMPLE_SIZE).map((c) => ({
        id: c.id,
        text: c.text,
        score: c.score,
      }));
      const res = await fetch(`${API_BASE}/comments/${videoId}/poll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ after: state.cursor, top_sample: topSample }),
      });
      const data = await res.json();
      if (data.comments.length) {
        mergeNewComments(data.comments);
        render();
      }
      if (data.cursor) {
        state.cursor = data.cursor;
      }
    } catch (err) {
      console.error("poll failed", err);
    } finally {
      schedulePoll();
    }
  }

  async function loadInitial() {
    const res = await fetch(`${API_BASE}/comments/${videoId}`);
    const data = await res.json();
    state.comments = data.comments;
    state.cursor = data.cursor;
    render();
    schedulePoll();
  }

  loadInitial();

  return () => {
    if (state.pollTimer) clearTimeout(state.pollTimer);
  };
}
