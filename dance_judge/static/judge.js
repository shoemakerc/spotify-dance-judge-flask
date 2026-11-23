// Small comforts on top of pages that work without any of this: a play
// button and playhead on the drawing, a copy-link button, and a sign that
// the judge is listening while the server works on the next page.

const heard = document.querySelector(".heard");
if (heard) {
  const audio = heard.querySelector("audio");
  const button = heard.querySelector(".heard-play");
  const playhead = heard.querySelector(".heard-playhead");
  const played = heard.querySelector("#heard-played rect");
  const width = heard.querySelector("svg").viewBox.baseVal.width;
  const seconds = Number(heard.dataset.duration);
  let frame = 0;

  // The browser's own controls were the fallback; the button replaces them.
  audio.controls = false;
  button.hidden = false;

  const draw = (fraction) => {
    const x = fraction * width;
    played.setAttribute("width", x);
    playhead.setAttribute("x1", x);
    playhead.setAttribute("x2", x);
    playhead.toggleAttribute("hidden", fraction <= 0);
  };
  const tick = () => {
    draw(audio.currentTime / (audio.duration || seconds));
    frame = requestAnimationFrame(tick);
  };

  button.addEventListener("click", () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()));
  audio.addEventListener("play", () => {
    button.textContent = "❚❚ Pause the preview";
    frame = requestAnimationFrame(tick);
  });
  audio.addEventListener("pause", () => {
    button.textContent = "▶ Play the preview";
    cancelAnimationFrame(frame);
  });
  audio.addEventListener("ended", () => draw(0));
}

const copy = document.querySelector(".copy-link");
if (copy && navigator.clipboard) {
  copy.hidden = false;
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      copy.textContent = "Link copied";
      setTimeout(() => (copy.textContent = "Copy link"), 2000);
    } catch {
      // Clipboard access denied; the address bar still has the link.
    }
  });
}

// Picking a song loads a new page, and the server takes a second to listen.
const judge = document.querySelector(".judge");
const listening = document.getElementById("judge-listening");
judge?.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="/song/"]');
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
  judge.classList.add("is-listening");
  listening.hidden = false;
});
// Coming back with the back button restores the page as it was left.
addEventListener("pageshow", () => {
  judge?.classList.remove("is-listening");
  if (listening) listening.hidden = true;
});
