// Start page: shown once per browser session; the SVCE logo reopens it.
// Visibility is the html.intro-open class. An inline script in <head> sets it
// before first paint on a first visit, so neither page ever flashes.
import { $, session } from "./util.js";

const SEEN_KEY = "stallion-intro-seen";

export function initIntro() {
  const root = document.documentElement;
  const intro = $("intro");
  let lastFocus = null;

  const sync = () => intro.setAttribute("aria-hidden", String(!root.classList.contains("intro-open")));

  function open() {
    lastFocus = document.activeElement;
    root.classList.add("intro-open");
    sync();
    setTimeout(() => $("intro-enter").focus(), 50);
  }
  function close() {
    root.classList.remove("intro-open", "intro-instant");
    session.set(SEEN_KEY, "1");
    sync();
    (lastFocus && lastFocus !== document.body ? lastFocus : $("top")).focus?.({ preventScroll: true });
  }

  $("intro-enter").addEventListener("click", close);
  $("about-btn").addEventListener("click", open);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && root.classList.contains("intro-open")) close();
  });

  sync();
  if (root.classList.contains("intro-open")) {
    setTimeout(() => $("intro-enter").focus(), 50);
    // Re-enable the fade for later open/close once the first frame is drawn
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("intro-instant")));
  }
}
