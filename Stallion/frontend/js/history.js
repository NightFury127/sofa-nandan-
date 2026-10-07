// Staff drawer: quote history and the rate editor, behind one staff key.
// Access needs the staff key when the server sets STALLION_STAFF_KEY;
// otherwise it only works from the server machine itself.
import { $, esc, fmt, mm, session, TYPE_LABELS } from "./util.js";
import { listQuotes, getQuote, getPricing, savePricing } from "./api.js";
import { renderRates, readRates } from "./rates.js";

const KEY_STORE = "stallion-staff-key";

export function initHistory({ onOpenQuote, onRatesSaved }) {
  const panel = $("history-panel");
  const status = $("history-status");
  const tabs = [$("staff-tab-quotes"), $("staff-tab-rates")];
  let current = "quotes";
  let loadedSheet = null;
  let returnFocus = null;

  // ── Drawer ────────────────────────────────────────────────────────────────
  function open() {
    returnFocus = document.activeElement;
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add("is-open"));
    document.body.classList.add("history-active");
    $("history-close").focus();
    load();
  }
  function close() {
    panel.classList.remove("is-open");
    document.body.classList.remove("history-active");
    setTimeout(() => { panel.hidden = true; }, 250);
    returnFocus?.focus?.();
  }

  // ── Tabs ──────────────────────────────────────────────────────────────────
  function selectTab(name, focus = false) {
    current = name;
    tabs.forEach(t => {
      const on = t.id === `staff-tab-${name}`;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      $(t.getAttribute("aria-controls")).hidden = !on;
      if (on && focus) t.focus();
    });
    load();
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => selectTab(t.id.replace("staff-tab-", "")));
    t.addEventListener("keydown", e => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      selectTab(tabs[(i + step + tabs.length) % tabs.length].id.replace("staff-tab-", ""), true);
    });
  });

  // ── Loading (shared staff-key handling) ───────────────────────────────────
  function needKey() {
    session.remove(KEY_STORE);
    status.textContent = "Staff tools need the staff key.";
    $("history-key-form").hidden = false;
    $("history-key").focus();
  }

  async function load() {
    $("history-key-form").hidden = true;
    status.textContent = "Loading…";
    try {
      if (current === "quotes") await loadQuotes();
      else await loadRates();
    } catch (err) {
      if (err.kind === "forbidden") needKey(); else status.textContent = err.message;
    }
  }

  async function loadQuotes() {
    const list = $("history-list");
    list.innerHTML = "";
    const { quotes } = await listQuotes(session.get(KEY_STORE));
    status.textContent = quotes.length ? `${quotes.length} most recent quotes` : "No quotes yet.";
    list.innerHTML = quotes.map(q => {
      const d = q.dimensions_mm || {};
      const when = q.created_at ? new Date(q.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";
      return `<li><button type="button" class="history-item" data-id="${esc(q.request_id)}">
        <span class="history-main"><b>${esc(q.customer_name || "Guest")}</b>
          <span>${esc(TYPE_LABELS[q.sofa_type] || q.sofa_type || "")} · ${mm(d.length)} × ${mm(d.width)} × ${mm(d.height)} mm</span></span>
        <span class="history-side"><b>₹${fmt(q.final_price)}</b><span>${esc(when)}</span></span>
      </button></li>`;
    }).join("");
  }

  async function loadRates() {
    loadedSheet = await getPricing(session.get(KEY_STORE));
    status.textContent = loadedSheet.note || "";
    renderRates(loadedSheet);
    wireDiscard();
  }
  function wireDiscard() {
    $("rates-discard").addEventListener("click", () => { renderRates(loadedSheet); wireDiscard(); });
  }

  // ── Events ────────────────────────────────────────────────────────────────
  // Top-bar button (desktop) and footer link (always visible, incl. phones)
  $("history-btn").addEventListener("click", open);
  document.querySelectorAll("[data-open-staff]").forEach(b => b.addEventListener("click", open));
  $("history-close").addEventListener("click", close);
  panel.addEventListener("click", e => { if (e.target === panel) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) close(); });

  $("history-key-form").addEventListener("submit", e => {
    e.preventDefault();
    session.set(KEY_STORE, $("history-key").value.trim());
    $("history-key").value = "";
    load();
  });

  $("history-list").addEventListener("click", async e => {
    const btn = e.target.closest(".history-item");
    if (!btn) return;
    status.textContent = "Opening quote…";
    try {
      const data = await getQuote(btn.dataset.id);
      close();
      onOpenQuote(data);
    } catch (err) {
      status.textContent = err.message;
    }
  });

  $("rates-form").addEventListener("submit", async e => {
    e.preventDefault();
    const form = $("rates-form");
    const out = $("rates-status");
    if (!form.reportValidity()) { out.textContent = "Fix the highlighted values first."; return; }
    out.textContent = "Saving…";
    try {
      const { pricing } = await savePricing(session.get(KEY_STORE), readRates(loadedSheet));
      loadedSheet = pricing;
      renderRates(loadedSheet);
      wireDiscard();
      $("rates-status").textContent = "Saved. New quotes use these rates; existing quotes keep their prices.";
      onRatesSaved?.(pricing);
    } catch (err) {
      if (err.kind === "forbidden") needKey(); else out.textContent = err.message;
    }
  });
}
