const videos = [...document.querySelectorAll("video")];
const localText = (ja, en) => document.documentElement.lang === "en" ? en : ja;

function showMediaError(element) {
  const container = element.closest(".media");
  const message = container?.querySelector(".media-error");
  if (message) message.hidden = false;
}

document.querySelectorAll("img").forEach((image) => {
  image.addEventListener("error", () => showMediaError(image));
  if (image.complete && !image.naturalWidth) showMediaError(image);
});

for (const video of videos) {
  video.addEventListener("error", () => showMediaError(video));
  video.querySelectorAll("source").forEach((source) => {
    source.addEventListener("error", () => showMediaError(video));
  });
  video.addEventListener("play", () => {
    for (const other of videos) {
      if (other !== video) other.pause();
    }
  });
}

for (const button of document.querySelectorAll(".video-toggle")) {
  const video = document.getElementById(button.dataset.video);
  if (!(video instanceof HTMLVideoElement)) {
    throw new Error(`Missing video for ${button.dataset.video}`);
  }
  button.hidden = false;
  const label = button.dataset.label;
  const update = () => {
    button.textContent = localText(`${label}を${video.paused ? "再生" : "一時停止"}`,
      `${video.paused ? "Play" : "Pause"} ${label}`);
  };
  update();
  video.addEventListener("play", update);
  video.addEventListener("pause", update);
  video.addEventListener("ended", update);
  button.addEventListener("click", async () => {
    if (!video.paused) {
      video.pause();
      return;
    }
    try {
      await video.play();
    } catch (error) {
      showMediaError(video);
      console.warn("Requested video playback could not start.", error.name);
    }
  });
}

const gifButton = document.getElementById("gif-toggle");
const preview = document.getElementById("gif-preview");
if (gifButton || preview) {
  if (!gifButton || !preview) throw new Error("Incomplete GIF preview controls");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const stillImage = preview.getAttribute("src");
  const stillAlt = preview.getAttribute("alt");

  function stopPreview() {
    if (gifButton.getAttribute("aria-pressed") !== "true") return;
    preview.src = stillImage;
    preview.alt = stillAlt;
    gifButton.setAttribute("aria-pressed", "false");
    gifButton.textContent = localText("歩行GIFを再生（33秒・約2.9 MB）", "Play walking GIF (33 s, about 2.9 MB)");
  }

  gifButton.hidden = false;
  gifButton.addEventListener("click", () => {
    if (gifButton.getAttribute("aria-pressed") === "true") {
      stopPreview();
      return;
    }
    for (const video of videos) video.pause();
    preview.src = gifButton.dataset.animation;
    preview.alt = localText("Ver.3.0 A・B・Cの旧規定歩行GIF。履歴・実機未検証、接触目標未達。",
      "Archived prescribed-input walking GIF of Ver.3.0 A, B and C. Physically unverified; contact targets unmet.");
    gifButton.setAttribute("aria-pressed", "true");
    gifButton.textContent = localText("GIFを停止して静止画に戻す", "Stop GIF and return to still image");
  });

  function applyMotionPreference() {
    document.getElementById("motion-preference").hidden = !reducedMotion.matches;
    if (reducedMotion.matches) stopPreview();
  }
  applyMotionPreference();
  reducedMotion.addEventListener("change", applyMotionPreference);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      videos.forEach((video) => video.pause());
      stopPreview();
    }
  });
}
