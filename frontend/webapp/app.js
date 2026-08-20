import { mountPanel, API_BASE } from "../panel/panel.js";

const DEFAULT_VIDEO_ID = "dQw4w9WgXcQ";
const params = new URLSearchParams(location.search);
const videoId = params.get("v") || DEFAULT_VIDEO_ID;

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

async function loadVideoMeta() {
  const res = await fetch(`${API_BASE}/video/${videoId}/insights`);
  const data = await res.json();

  document.getElementById("video-title").textContent = data.title;
  document.getElementById("video-channel").textContent = data.channel_title;

  const panelHandle = mountPanel(document.getElementById("panel"), {
    videoId,
    getPlaybackState,
    summary: data.summary,
    insights: data.insights,
    onReady: () => {
      document.getElementById("loading-overlay").classList.add("hidden");
    },
  });

  setupResizableDivider(panelHandle);
}

loadVideoMeta();
