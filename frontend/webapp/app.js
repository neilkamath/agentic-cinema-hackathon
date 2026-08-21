import { mountPanel, API_BASE } from "../panel/panel.js";

const DEFAULT_VIDEO_ID = "dQw4w9WgXcQ";
const params = new URLSearchParams(location.search);
const videoId = params.get("v") || DEFAULT_VIDEO_ID;

// Carry a local-backend override back to the homepage, same as the homepage
// carries it forward here - so the round trip keeps pointing at the same
// backend during local testing instead of silently falling back to Cloud Run.
const apiOverride = params.get("api");
if (apiOverride) {
  document.getElementById("back-link").href = `../index.html?api=${encodeURIComponent(apiOverride)}`;
}

let player = null;

function createPlayer() {
  player = new YT.Player("player", {
    videoId,
    width: "100%",
    height: "100%",
  });
}

// The YouTube API script can finish loading and try to call this before our
// own deferred module script runs, so check for an already-ready API instead
// of assuming the callback will always fire after we register it.
if (window.YT && window.YT.Player) {
  createPlayer();
} else {
  window.onYouTubeIframeAPIReady = createPlayer;
}

function getPlaybackState() {
  if (!player || typeof player.getDuration !== "function") return null;
  const duration = player.getDuration();
  if (!duration) return null;
  return {
    currentTime: player.getCurrentTime(),
    duration,
    paused: player.getPlayerState() !== YT.PlayerState.PLAYING,
  };
}

function seekTo(seconds) {
  if (player && typeof player.seekTo === "function") {
    player.seekTo(seconds, true);
  }
}

function setupResizableDivider(panelHandle) {
  const app = document.getElementById("app");
  const chatColumn = document.getElementById("chat-column");
  const divider = document.getElementById("divider");

  const MIN_MAIN_WIDTH = 360;
  const MIN_CHAT_WIDTH = 280;
  let dragging = false;

  divider.addEventListener("pointerdown", (e) => {
    dragging = true;
    divider.classList.add("dragging");
    divider.setPointerCapture(e.pointerId);
    document.body.style.userSelect = "none";
    // Resizing reflows comment/insight text, which can shrink the panel's
    // scrollHeight enough that the browser clamps scrollTop on its own -
    // that's not the viewer scrolling, so don't let it pause/resume the chat.
    panelHandle?.setScrollSuspended(true);
  });

  divider.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const appRect = app.getBoundingClientRect();
    const dividerWidth = divider.getBoundingClientRect().width;
    const maxChatWidth = appRect.width - MIN_MAIN_WIDTH - dividerWidth;
    const rawChatWidth = appRect.right - e.clientX;
    const chatWidth = Math.min(maxChatWidth, Math.max(MIN_CHAT_WIDTH, rawChatWidth));
    chatColumn.style.width = `${chatWidth}px`;
  });

  function stopDragging() {
    if (!dragging) return;
    dragging = false;
    divider.classList.remove("dragging");
    document.body.style.userSelect = "";
    panelHandle?.setScrollSuspended(false);
  }
  divider.addEventListener("pointerup", stopDragging);
  divider.addEventListener("pointercancel", stopDragging);
}

// The homepage's start popup may have already fetched both comments and
// insights before navigating here, so this page opens fully populated
// instead of loading anything itself. One-time use - if the viewer comes
// back to this same page later (back/forward, refresh), it's stale.
const PRELOAD_KEY = `sidecast:preload:${videoId}`;
let preload = null;
const preloadRaw = sessionStorage.getItem(PRELOAD_KEY);
if (preloadRaw) {
  sessionStorage.removeItem(PRELOAD_KEY);
  try {
    preload = JSON.parse(preloadRaw);
  } catch (err) {
    console.error("failed to parse preloaded data, falling back to a normal load", err);
  }
}

// The insights call is the expensive part (Gemini + Parallel Search), so it
// doesn't fire on page load - only once the viewer deliberately clicks in
// (or immediately, if the data was already preloaded from the homepage).
// Until it does, the video and the back button are already fully usable, so
// a misclick into the wrong video costs nothing to back out of.
async function loadVideoMeta() {
  let data;
  if (preload) {
    data = preload.insights;
  } else {
    const startFeed = document.getElementById("start-feed");
    startFeed.innerHTML = `<div class="loading-spinner"></div><div id="start-feed-hint">Setting up Sidecast…</div>`;
    const res = await fetch(`${API_BASE}/video/${videoId}/insights`);
    data = await res.json();
  }

  document.getElementById("video-title").textContent = data.title;
  document.getElementById("video-channel").textContent = data.channel_title;

  const panelHandle = mountPanel(document.getElementById("panel"), {
    videoId,
    getPlaybackState,
    seekTo,
    summary: data.summary,
    insights: data.insights,
    preloadedComments: preload?.comments,
  });

  setupResizableDivider(panelHandle);
}

if (preload) {
  loadVideoMeta();
} else {
  document.getElementById("start-feed-button").addEventListener("click", loadVideoMeta, { once: true });
}
