// Entry point: wires the modules together and switches between the
// form, processing, results and error views.
import { $ } from "./util.js";
import { getConfig, postQuote, ApiError } from "./api.js";
import { initIntro } from "./intro.js";
import { initForm } from "./form.js";
import { newProgressId, startProgress } from "./progress.js";
import { initResults, renderResults, renderError } from "./results.js";
import { initHistory } from "./history.js";
import { initNav } from "./nav.js";

const views = {
  form:       () => [$("configure")],
  processing: () => [$("processing")],
  results:    () => [$("results")],
  error:      () => [$("reject-section")],
};

function show(view) {
  for (const [name, els] of Object.entries(views)) {
    els().forEach(el => {
      const on = name === view;
      if (el.classList.contains("processing") || el.id === "results" || el.id === "reject-section") {
        el.classList.toggle("show", on);
      } else {
        el.style.display = on ? "" : "none";
      }
    });
  }
}

function focusHeading(el) {
  if (!el) return;
  el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: true });
  window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + window.scrollY - 100), behavior: "smooth" });
}

async function main() {
  initIntro();
  initResults();
  initNav();

  let config = null;
  try { config = await getConfig(); }
  catch (err) { console.warn("Could not load size limits; the server will still check them.", err); }

  function showResults(data) {
    renderResults(data);
    show("results");
    focusHeading(document.querySelector("#results h2"));
  }

  const form = initForm({
    config,
    onSubmit: async formData => {
      const progressId = newProgressId();
      formData.append("progress_id", progressId);
      show("processing");
      focusHeading($("processing-title"));
      const progress = startProgress(progressId);
      try {
        const data = await postQuote(formData);
        progress.stop(true);
        showResults(data);
      } catch (err) {
        progress.stop(false);
        renderError(err instanceof ApiError ? err : new ApiError("server", String(err)));
        show("error");
        focusHeading($("reject-title"));
      }
    },
  });

  initHistory({ onOpenQuote: showResults });

  $("new-request-btn").addEventListener("click", () => {
    form.reset();
    show("form");
    focusHeading(document.querySelector("#configure h2"));
  });
  // "Back to the form" keeps what was entered, so a fix doesn't mean starting over
  $("retry-btn").addEventListener("click", () => {
    show("form");
    focusHeading(document.querySelector("#configure h2"));
  });

  document.addEventListener("mousemove", e => {
    document.documentElement.style.setProperty("--mx", e.clientX + "px");
    document.documentElement.style.setProperty("--my", e.clientY + "px");
  });
}

main();
