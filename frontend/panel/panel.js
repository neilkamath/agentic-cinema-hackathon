const DEFAULT_API_BASE = "https://yt-curator-backend-659579556690.us-central1.run.app";
export const API_BASE = new URLSearchParams(location.search).get("api") || DEFAULT_API_BASE;

const POLL_INTERVAL_MS = 15000;
const SCROLL_TOLERANCE_PX = 4;

const ICONS = {
  thumbsUp:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>',
  arrowDown:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>',
  externalLink:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
  background:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="12" y2="16"/></svg>',
  did_you_know:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.93 4.93 2.83 2.83"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/></svg>',
  deeper_dive:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 10 6-10 6L2 9Z"/><path d="m2 15 10 6 10-6"/></svg>',
  related_event:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/></svg>',
};

const CATEGORY_LABELS = {
  background: "Background",
  did_you_know: "Did You Know",
  deeper_dive: "Deeper Dive",
  related_event: "Related Event",
};

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

function renderSummaryCard(summary) {
  const row = document.createElement("div");
  row.className = "summary-card";

  const label = document.createElement("div");
  label.className = "summary-label";
  label.textContent = "About this video";
  row.appendChild(label);

  const text = document.createElement("div");
  text.className = "summary-text";
  text.textContent = summary;
  row.appendChild(text);

  return row;
}

function renderComment(comment) {
  const row = document.createElement("div");
  row.className = "comment";

  const avatar = document.createElement("img");
  avatar.className = "avatar";
  avatar.src = comment.author_avatar_url;
  avatar.alt = "";
  // Comments are all frontloaded into the DOM at once (see mountPanel) so the
  // scroll glide has something to reveal smoothly - lazy-loading means the
  // browser only actually fetches an avatar once it nears the viewport,
  // pacing real network requests instead of bursting all of them at once
  // against YouTube's rate-limited avatar CDN (yt3.ggpht.com).
  avatar.loading = "lazy";
  // An avatar that fails to load (e.g. still rate-limited) should fall back
  // to the plain background circle instead of showing a broken-image glyph.
  avatar.addEventListener("error", () => { avatar.style.visibility = "hidden"; }, { once: true });
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

function renderInsightCard(insight) {
  const row = document.createElement("div");
  row.className = "insight-card";

  const icon = ICONS[insight.category] || ICONS.did_you_know;
  const categoryLabel = CATEGORY_LABELS[insight.category] || "Insight";

  const label = document.createElement("div");
  label.className = "insight-label";
  label.innerHTML = `${icon}<span>${categoryLabel}</span>`;
  row.appendChild(label);

  const headline = document.createElement("div");
  headline.className = "insight-headline";
  headline.textContent = insight.headline;
  row.appendChild(headline);

  if (insight.video_reference) {
    const videoReference = document.createElement("div");
    videoReference.className = "insight-video-reference";
    videoReference.textContent = insight.video_reference;
    row.appendChild(videoReference);
  }

  const text = document.createElement("div");
  text.className = "insight-text";
  text.textContent = insight.text;
  row.appendChild(text);

  if (insight.source_url) {
    const source = document.createElement("a");
    source.className = "insight-source";
    source.href = insight.source_url;
    source.target = "_blank";
    source.rel = "noopener";
    source.innerHTML = `<span>source</span>${ICONS.externalLink}`;
    row.appendChild(source);
  }

  return row;
}

export function mountPanel(container, { videoId, getPlaybackState, onReady, summary, insights }) {
  container.innerHTML = "";
  const list = document.createElement("div");
  list.className = "comment-list";
  container.appendChild(list);

  if (summary) {
    list.appendChild(renderSummaryCard(summary));
  }

  const feed = document.createElement("div");
  feed.className = "comment-feed";
  list.appendChild(feed);

  const state = {
    comments: [],
    // Insight cards only get embedded with a real transcript-anchored
    // timestamp - no interpolated placement for these, unlike comments
    // below. An insight without one is simply left out of the feed.
    insights: (insights || []).filter((i) => i.timestamp_seconds != null),
    // Sorted array of { type: "comment"|"insight", id, effectiveTimestamp } -
    // the single merged order the feed renders in.
    sequence: [],
    merged: false,
    // The video duration used to interpolate comment timestamps at merge
    // time. YouTube often plays a short pre-roll ad before the real video
    // starts, during which getDuration() reports the ad's (much shorter)
    // duration - if that's what's available the first time we check, merge
    // happens against the wrong number entirely. Tracked so glideLoop can
    // detect when the real duration shows up afterward and rescale.
    mergedDuration: null,
    cursor: null,
    pollTimer: null,
    rafId: null,
    autoGlide: true,
    lastTarget: 0,
  };

  const renderedNodes = new Map();

  // Overlaid on the panel's non-scrolling parent, not `container` itself -
  // an absolutely positioned child of the scroll container would scroll away
  // with the content instead of floating in place like Twitch/YouTube's
  // "jump to current" pill does.
  const jumpButton = document.createElement("button");
  jumpButton.type = "button";
  jumpButton.className = "jump-to-current";
  jumpButton.innerHTML = `${ICONS.arrowDown}<span>Jump back</span>`;
  jumpButton.addEventListener("click", () => {
    state.autoGlide = true;
    jumpButton.classList.remove("visible");
    scrollToTarget({ smooth: true });
  });
  (container.parentElement || container).appendChild(jumpButton);

  // The scroll position that exactly matches the video's current state -
  // a pure function of currentTime/duration, recomputed fresh every call
  // with no memory of "where we came from". That's what makes it immune to
  // pausing, seeking, and playback-speed changes: however currentTime got
  // to its current value, this is always the correct proportional position.
  function baseTargetFor(playback) {
    if (!playback || !playback.duration) return 0;
    const maxScroll = container.scrollHeight - container.clientHeight;
    if (maxScroll <= 0) return 0;
    const fraction = Math.min(1, Math.max(0, playback.currentTime / playback.duration));
    return fraction * maxScroll;
  }

  // Scroll position deviating from `state.lastTarget` (the position we last
  // set ourselves) means the viewer scrolled manually - pause the glide
  // indefinitely. It only ever auto-scrolls while in sync with the video;
  // once the viewer scrolls away, it stays put until they click "Jump back"
  // (no cooldown, no automatic resume).
  //
  // Resizing the video/chat divider changes the panel's width, which
  // reflows comment/insight text and changes its total height - if that
  // shrinks scrollHeight below the current scrollTop, the browser clamps
  // scrollTop on its own and fires a real `scroll` event for it. That's not
  // the viewer scrolling, so callers doing the resizing (see
  // `setScrollSuspended` below) can tell us to ignore scroll events for the
  // duration - this leaves autoGlide untouched either way, so a synced chat
  // stays synced through a resize and an already-paused one stays paused.
  let scrollSuspended = false;
  function handleScroll() {
    if (scrollSuspended) return;
    if (Math.abs(container.scrollTop - state.lastTarget) > SCROLL_TOLERANCE_PX) {
      state.autoGlide = false;
      jumpButton.classList.add("visible");
    }
  }
  container.addEventListener("scroll", handleScroll);

  const loading = document.createElement("div");
  loading.className = "loading";
  loading.textContent = "Loading comments…";
  feed.appendChild(loading);

  function renderItem(item) {
    return item.type === "insight" ? renderInsightCard(item.data) : renderComment(item.data);
  }

  // First render, once video duration is known: comments get an interpolated
  // timestamp (evenly spread across the video, in fetched order - the same
  // fallback comments have always used), insights use their real
  // transcript-anchored timestamp. Merging both into one sorted sequence and
  // frontloading every node is what lets the glide reveal them smoothly
  // together instead of comments and insights living in separate places.
  function mergeInitial(duration) {
    const items = state.comments.map((comment, i) => ({
      type: "comment",
      id: comment.id,
      data: comment,
      effectiveTimestamp: ((i + 1) / state.comments.length) * duration,
    }));
    for (const insight of state.insights) {
      items.push({
        type: "insight",
        id: insight.id,
        data: insight,
        effectiveTimestamp: insight.timestamp_seconds,
      });
    }
    items.sort((a, b) => a.effectiveTimestamp - b.effectiveTimestamp);
    state.sequence = items;
    state.mergedDuration = duration;

    loading.remove();
    for (const item of items) {
      const node = renderItem(item);
      renderedNodes.set(item.id, node);
      feed.appendChild(node);
    }
    if (!items.length) {
      const hint = document.createElement("div");
      hint.className = "loading";
      hint.textContent = "Comments will appear as you watch…";
      feed.appendChild(hint);
    }
    state.merged = true;
  }

  // Comments were interpolated against `state.mergedDuration` at merge time -
  // if the real duration later turns out to be different (e.g. a pre-roll ad
  // reported its own short duration first), rescale every comment's
  // timestamp to match instead of leaving them frozen against the wrong
  // number. Insight timestamps are real content positions, not interpolated
  // against duration at all, so they're untouched.
  function rescaleComments(newDuration) {
    const ratio = newDuration / state.mergedDuration;
    for (const item of state.sequence) {
      if (item.type === "comment") {
        item.effectiveTimestamp *= ratio;
      }
    }
    state.sequence.sort((a, b) => a.effectiveTimestamp - b.effectiveTimestamp);
    state.mergedDuration = newDuration;
    for (const item of state.sequence) {
      const node = renderedNodes.get(item.id);
      if (node) feed.appendChild(node);
    }
  }

  // Comments arriving after the initial merge (via poll) are placed at
  // roughly the current video moment - they just appeared, same as a live
  // chat message would - and inserted into the sorted sequence rather than
  // just appended, since "now" can land before already-rendered items that
  // were interpolated further ahead.
  function insertComment(comment, currentTime) {
    if (renderedNodes.has(comment.id)) return;
    const item = { type: "comment", id: comment.id, data: comment, effectiveTimestamp: currentTime };

    let idx = state.sequence.findIndex((s) => s.effectiveTimestamp > currentTime);
    if (idx === -1) idx = state.sequence.length;
    state.sequence.splice(idx, 0, item);

    const node = renderComment(comment);
    renderedNodes.set(comment.id, node);
    const nextItem = state.sequence[idx + 1];
    const nextNode = nextItem ? renderedNodes.get(nextItem.id) : null;
    if (nextNode) {
      feed.insertBefore(node, nextNode);
    } else {
      feed.appendChild(node);
    }
  }

  function scrollToTarget({ smooth }) {
    const playback = getPlaybackState ? getPlaybackState() : null;
    if (!playback || !playback.duration) return;

    const maxScroll = container.scrollHeight - container.clientHeight;
    if (maxScroll <= 0) return;

    const target = baseTargetFor(playback);
    state.lastTarget = target;
    if (smooth) {
      container.scrollTo({ top: target, behavior: "smooth" });
    } else {
      container.scrollTop = target;
    }
  }

  function glideLoop() {
    const playback = getPlaybackState ? getPlaybackState() : null;
    let justCorrectedDuration = false;
    if (!state.merged && playback && playback.duration) {
      mergeInitial(playback.duration);
    } else if (state.merged && playback && playback.duration && Math.abs(playback.duration - state.mergedDuration) > 1) {
      rescaleComments(playback.duration);
      justCorrectedDuration = true;
    }

    if (state.autoGlide) {
      // getDuration() can report a wrong, unstable value for a moment right
      // at video start before settling - when rescaleComments just corrected
      // for that, animate the resulting position change instead of snapping
      // straight to it, so a big one-time correction reads as a smooth
      // scroll rather than a jarring jump.
      scrollToTarget({ smooth: justCorrectedDuration });
    }
    state.rafId = requestAnimationFrame(glideLoop);
  }

  function schedulePoll() {
    state.pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }

  async function poll() {
    try {
      const res = await fetch(`${API_BASE}/comments/${videoId}/poll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ after: state.cursor }),
      });
      const data = await res.json();
      const playback = getPlaybackState ? getPlaybackState() : null;
      for (const comment of data.comments) {
        state.comments.push(comment);
        if (state.merged && playback && playback.duration) {
          insertComment(comment, playback.currentTime);
        }
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

    state.cursor = data.cursor;
    state.comments = data.comments;

    // Merging (and clearing the loading placeholder) happens in glideLoop
    // once video duration is known - see mergeInitial.
    state.rafId = requestAnimationFrame(glideLoop);
    schedulePoll();
    onReady?.();
  }

  loadInitial();

  return {
    destroy: () => {
      if (state.pollTimer) clearTimeout(state.pollTimer);
      if (state.rafId) cancelAnimationFrame(state.rafId);
      container.removeEventListener("scroll", handleScroll);
      jumpButton.remove();
    },
    // Lets a caller that's about to reflow the panel's layout (e.g. dragging
    // a video/chat divider) suppress scroll-triggered pause detection for
    // the duration, so a browser-driven scrollTop clamp from the reflow
    // doesn't get mistaken for the viewer scrolling. See `handleScroll`.
    setScrollSuspended: (suspended) => {
      scrollSuspended = suspended;
    },
  };
}
