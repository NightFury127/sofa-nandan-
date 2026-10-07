// Highlights the menu item for the section currently on screen.
// The quote form, progress, results and error views all belong to "Get a quote".

const SECTION_TO_LINK = {
  problem: "#problem",
  how: "#how",
  configure: "#configure",
  processing: "#configure",
  results: "#configure",
  "reject-section": "#configure",
  svce: "#svce",
};

export function initNav() {
  const links = [...document.querySelectorAll('.nav a[href^="#"]')];
  const sections = Object.keys(SECTION_TO_LINK).map(id => document.getElementById(id)).filter(Boolean);
  const visible = new Map();

  const update = () => {
    // The section whose top is nearest below the header wins
    let best = null;
    for (const [el, top] of visible) if (best === null || Math.abs(top) < Math.abs(visible.get(best))) best = el;
    const href = best ? SECTION_TO_LINK[best.id] : null;
    links.forEach(a => {
      if (a.getAttribute("href") === href) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  };

  const observer = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (e.isIntersecting) visible.set(e.target, e.boundingClientRect.top - 90);
      else visible.delete(e.target);
    }
    update();
  }, { rootMargin: "-90px 0px -45% 0px", threshold: [0, 0.25, 0.5] });

  sections.forEach(s => observer.observe(s));
}
