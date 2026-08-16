const DEFAULT_API_BASE = "https://yt-curator-backend-659579556690.us-central1.run.app";
const API_BASE = new URLSearchParams(location.search).get("api") || DEFAULT_API_BASE;

const REVEAL_TICK_MS = 1000;
const POLL_INTERVAL_MS = 15000;
const TOP_SAMPLE_SIZE = 15;
const SCROLL_BOTTOM_THRESHOLD = 24;

const ICONS = {
  thumbsUp:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>',
  externalLink:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
  arrowDown:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>',
};

function scoreToOpacity(score) {
  const clamped = Math.max(0, Math.min(100, score));
  return 0.35 + (clamped / 100) * 0.65;
}

const RELATIVE_TIME_UNITS = [
  ["year", 31536000],
  ["month", 2592000],
  ["week", 604800],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

function formatRelativeTime(isoString) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  for (const [name, secondsInUnit] of RELATIVE_TIME_UNITS) {
    const value = Math.floor(seconds / secondsInUnit);
    if (value >= 1) {
      return `${value} ${name}${value > 1 ? "s" : ""} ago`;
    }
  }
  return "just now";
}

function renderComment(comment) {
  const row = document.createElement("div");
  row.className = "comment";
  row.style.opacity = scoreToOpacity(comment.score);

  const avatar = document.createElement("img");
  avatar.className = "avatar";
  avatar.src = comment.author_avatar_url;
  avatar.alt = "";
  row.appendChild(avatar);

  const body = document.createElement("div");
  body.className = "comment-body";

  const header = document.createElement("div");
  header.className = "comment-header";

  const author = document.createElement("span");
  author.className = "author";
  author.textContent = comment.author;
  header.appendChild(author);

  const postedAt = document.createElement("span");
  postedAt.className = "posted-at";
  postedAt.textContent = formatRelativeTime(comment.published_at);
  header.appendChild(postedAt);

  body.appendChild(header);

  const text = document.createElement("div");
  text.className = "comment-text";
  text.textContent = comment.text;
  body.appendChild(text);

  const likes = document.createElement("span");
  likes.className = "likes";
  likes.innerHTML = `${ICONS.thumbsUp}<span>${comment.like_count}</span>`;
  body.appendChild(likes);

  row.appendChild(body);

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
    source.innerHTML = `<span>source</span>${ICONS.externalLink}`;
    row.appendChild(source);
  }

  return row;
}

export function mountPanel(container, { videoId, getPlaybackState, onReady, onMeta }) {
  container.innerHTML = "";
  const list = document.createElement("div");
  list.className = "comment-list";
  container.appendChild(list);

  // Overlaid on the panel's non-scrolling parent, not `container` itself -
  // an absolutely positioned child of the scroll container would scroll away
  // with the content instead of floating in place like Twitch/YouTube's
  // "jump to current" pill does.
  const jumpButton = document.createElement("button");
  jumpButton.type = "button";
  jumpButton.className = "jump-to-current";
  jumpButton.innerHTML = `${ICONS.arrowDown}<span>Jump to current</span>`;
  jumpButton.addEventListener("click", () => {
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  });
  (container.parentElement || container).appendChild(jumpButton);

  function updateJumpButtonVisibility() {
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    jumpButton.classList.toggle("visible", distanceFromBottom > SCROLL_BOTTOM_THRESHOLD);
  }
  container.addEventListener("scroll", updateJumpButtonVisibility);

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
    const totalComments = state.comments.length;
    const numFacts = state.facts.length;
    let factIdx = 0;

    state.comments.forEach((comment, i) => {
      seq.push({ type: "comment", data: comment });
      // Spread facts evenly across the whole comment list rather than a fixed
      // interval, which would cluster them all near the front once the (much
      // smaller) fact pool runs out. A `while`, not `if`, so a video with very
      // few comments still surfaces every fact instead of silently dropping some.
      while (factIdx < numFacts && (factIdx + 1) / (numFacts + 1) <= (i + 1) / totalComments) {
        seq.push({ type: "fact", data: state.facts[factIdx] });
        factIdx++;
      }
    });
    while (factIdx < numFacts) {
      seq.push({ type: "fact", data: state.facts[factIdx] });
      factIdx++;
    }

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
    updateJumpButtonVisibility();
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
    onMeta?.({ title: factsData.title, channelTitle: factsData.channel_title });
    onReady?.();
  }

  loadInitial();

  return () => {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    if (state.revealTimer) clearInterval(state.revealTimer);
    container.removeEventListener("scroll", updateJumpButtonVisibility);
    jumpButton.remove();
  };
}
