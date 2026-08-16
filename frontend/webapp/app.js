import { mountPanel } from "../panel/panel.js";

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
  return { currentTime: player.getCurrentTime(), duration };
}

mountPanel(document.getElementById("panel"), { videoId, getPlaybackState });
