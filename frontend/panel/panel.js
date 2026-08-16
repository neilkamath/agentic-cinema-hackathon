const DEFAULT_API_BASE = "https://yt-curator-backend-659579556690.us-central1.run.app";
const API_BASE = new URLSearchParams(location.search).get("api") || DEFAULT_API_BASE;

const REVEAL_TICK_MS = 1000;
const FACT_CARD_INTERVAL = 6;
const POLL_INTERVAL_MS = 15000;
const TOP_SAMPLE_SIZE = 15;
const SCROLL_BOTTOM_THRESHOLD = 24;

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

  row.appendChild(header);

  const text = document.createElement("div");
  text.className = "comment-text";
  text.textContent = comment.text;
  row.appendChild(text);

  return row;
}

function renderFactCard(fact) {
  const row = document.createElement("div");
  row.className = "fact-card";

  const label = document.createElement("div");
  label.className = "fact-label";
  label.textContent = "AI Insight";
  row.appendChild(label);

  const text = document.createElement("div");
  text.className = "fact-text";
  text.textContent = fact.text;
  row.appendChild(text);

  if (fact.source_url) {
    const source = document.createElement("a");
    source.className = "fact-source";
    source.href = fact.source_url;
    source.target = "_blank";
    source.rel = "noopener";
    source.textContent = "source";
    row.appendChild(source);
  }

  return row;
}

export function mountPanel(container, { videoId, getPlaybackState }) {
  container.innerHTML = "";
  const list = document.createElement("div");
  list.className = "comment-list";
  container.appendChild(list);

  const state = {
    comments: [],
    facts: [],
    sequence: [],
    revealedCount: 0,
    cursor: null,
    pollTimer: null,
    revealTimer: null,
  };

  const loading = document.createElement("div");
  loading.className = "loading";
  loading.textContent = "Loading comments…";
  list.appendChild(loading);

  function buildSequence() {
    const seq = [];
    let factIdx = 0;
    state.comments.forEach((comment, i) => {
      seq.push({ type: "comment", data: comment });
      if ((i + 1) % FACT_CARD_INTERVAL === 0 && factIdx < state.facts.length) {
        seq.push({ type: "fact", data: state.facts[factIdx] });
        factIdx++;
      }
    });
    state.sequence = seq;
  }

  function render() {
    // `container` (#panel) is the actual scroll container (overflow-y: auto in
    // panel.css) - `list` just grows unconstrained inside it, so scroll position
    // must be read/written on `container`, not `list`.
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const wasPinnedToBottom = distanceFromBottom <= SCROLL_BOTTOM_THRESHOLD;
    const previousScrollTop = container.scrollTop;

    list.innerHTML = "";
    const visible = state.sequence.slice(0, state.revealedCount);
    if (!visible.length) {
      const hint = document.createElement("div");
      hint.className = "loading";
      hint.textContent = "Comments will appear as you watch…";
      list.appendChild(hint);
    } else {
      for (const item of visible) {
        list.appendChild(item.type === "fact" ? renderFactCard(item.data) : renderComment(item.data));
      }
    }

    container.scrollTop = wasPinnedToBottom ? container.scrollHeight : previousScrollTop;
  }

  function tickReveal() {
    const playback = getPlaybackState ? getPlaybackState() : null;
    if (!playback || !playback.duration) return;

    buildSequence();
    const fraction = Math.min(1, Math.max(0, playback.currentTime / playback.duration));
    const target = Math.floor(fraction * state.sequence.length);
    if (target !== state.revealedCount) {
      state.revealedCount = target;
      render();
    }
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
        state.comments.push(...data.comments);
        state.comments.sort((a, b) => b.score - a.score);
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
    const [commentsRes, factsRes] = await Promise.all([
      fetch(`${API_BASE}/comments/${videoId}`),
      fetch(`${API_BASE}/video/${videoId}/facts`),
    ]);
    const commentsData = await commentsRes.json();
    const factsData = await factsRes.json();

    state.comments = commentsData.comments;
    state.cursor = commentsData.cursor;
    state.facts = factsData.facts;
    buildSequence();
    render();

    state.revealTimer = setInterval(tickReveal, REVEAL_TICK_MS);
    schedulePoll();
  }

  loadInitial();

  return () => {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    if (state.revealTimer) clearInterval(state.revealTimer);
  };
}
