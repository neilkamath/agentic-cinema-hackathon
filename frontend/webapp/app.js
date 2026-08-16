import { mountPanel } from "../panel/panel.js";

const DEFAULT_VIDEO_ID = "dQw4w9WgXcQ";
const params = new URLSearchParams(location.search);
const videoId = params.get("v") || DEFAULT_VIDEO_ID;

function createPlayer() {
  new YT.Player("player", {
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

mountPanel(document.getElementById("panel"), { videoId });
