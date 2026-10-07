// Real progress: polls /api/progress/{id} while the quote request runs and
// shows which pipeline step the server is on.
import { $ } from "./util.js";
import { getProgress } from "./api.js";

// Mirrors PROGRESS_STEPS in src/api.py (without the final "done").
const STEPS = [
  ["upload",  "Receiving the photo"],
  ["image",   "Checking the image"],
  ["detect",  "Detecting the sofa and its parts"],
  ["cost",    "Scaling the bill of materials and pricing"],
  ["drawing", "Drawing the technical views"],
  ["model3d", "Building the 3D model"],
  ["step",    "Writing the CAD (STEP) file"],
];

export function newProgressId() {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

export function startProgress(progressId) {
  const list = $("progress-steps");
  list.innerHTML = STEPS.map(([key, label]) =>
    `<li data-step="${key}"><span class="step-dot" aria-hidden="true"></span>${label}</li>`).join("");
  const started = Date.now();
  let current = -1;
  let stopped = false;

  function show(index) {
    if (index <= current) return;
    current = index;
    [...list.children].forEach((li, i) => {
      li.classList.toggle("done", i < index);
      li.classList.toggle("active", i === index);
      if (i === index) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
    const label = STEPS[index]?.[1] || "Finishing up";
    $("processing-title").textContent = label.toUpperCase();
    $("process-status").textContent = `STEP ${Math.min(index + 1, STEPS.length)} OF ${STEPS.length}`;
    $("progress-bar").style.width = `${Math.round(((index + 0.5) / STEPS.length) * 100)}%`;
  }

  async function poll() {
    while (!stopped) {
      const p = await getProgress(progressId);
      if (p && typeof p.index === "number") show(Math.min(p.index, STEPS.length - 1));
      $("processing-elapsed").textContent = `${Math.round((Date.now() - started) / 1000)} s elapsed`;
      await new Promise(r => setTimeout(r, 700));
    }
  }

  show(0);
  poll();
  return {
    stop(success) {
      stopped = true;
      if (success) {
        [...list.children].forEach(li => { li.classList.add("done"); li.classList.remove("active"); });
        $("progress-bar").style.width = "100%";
      }
    },
  };
}
