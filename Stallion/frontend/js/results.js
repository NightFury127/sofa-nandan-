// Results page: detection, dimensions, price, BOM, cost structure, CAD files,
// the 3D viewer and the PDF download. Also the error/rejection screen.
import { $, esc, fmt, mm, TYPE_LABELS } from "./util.js";
import { getSizeOptions } from "./api.js";

const COMPONENT_NAMES = {
  seat_cushion: "SEAT CUSHION", back_cushion: "BACK CUSHION", right_arm: "RIGHT ARM",
  left_arm: "LEFT ARM", legs: "LEGS", base: "BASE",
};

// ── Inspection viewer (full-screen annotated photo) ──────────────────────────
let viewerReturnFocus = null;

function openInspection() {
  const source = $("annotated-img");
  if (!source.getAttribute("src")) return;
  viewerReturnFocus = document.activeElement;
  $("inspection-viewer-img").src = source.src;
  $("inspection-viewer-type").textContent = $("detected-type").textContent || "SOFA";
  $("inspection-viewer-confidence").textContent = $("conf-label").textContent || "—";
  $("inspection-viewer-meta").textContent = $("detected-meta").textContent || "—";
  const viewer = $("inspection-viewer");
  viewer.classList.add("is-open");
  viewer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  $("inspection-close").focus();
}

function closeInspection() {
  const viewer = $("inspection-viewer");
  if (!viewer.classList.contains("is-open")) return;
  viewer.classList.remove("is-open");
  viewer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  viewerReturnFocus?.focus?.();
}

// ── Result media: 3D model / detection photo tabs ────────────────────────────
const TABS = () => [$("tab-3d"), $("tab-photo")];

function selectTab(tab, focus = false) {
  TABS().forEach(t => {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  });
  $("media-fullscreen").hidden = tab.id !== "tab-3d";
  if (focus) tab.focus();
}

export function initResults() {
  initModelControls();
  $("photo-enlarge").addEventListener("click", openInspection);
  $("inspection-close").addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); closeInspection(); });
  $("inspection-viewer").addEventListener("click", e => { if (e.target.id === "inspection-viewer") closeInspection(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeInspection(); });

  TABS().forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", e => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const visible = TABS().filter(t => !t.hidden);
      selectTab(visible[(visible.indexOf(tab) + step + visible.length) % visible.length], true);
    });
  });

  $("media-fullscreen").addEventListener("click", () => {
    const panel = $("result-3d");
    if (document.fullscreenElement) document.exitFullscreen();
    else panel.requestFullscreen?.().catch(() => {});
  });
}

// ── 3D viewer: <model-viewer>, loaded only when a model exists ───────────────
let modelViewerLoad = null;

// Each layer of the model has its own material (see cad_generator_3d.LAYER_COLOURS).
// Hiding fabric, then foam, opens the sofa up to the springs, webbing and frame.
const LAYER_GROUPS = {
  fabric: ["fabric"],
  foam: ["seat_foam", "back_foam", "padding"],
};
const modelState = { exploded: false, hidden: new Set(), urls: {} };

function applyLayers(mv) {
  if (!mv?.model) return;
  const hide = new Set([...modelState.hidden].flatMap(group => LAYER_GROUPS[group]));
  for (const material of mv.model.materials) {
    const hidden = hide.has(material.name);
    const [r, g, b] = material.pbrMetallicRoughness.baseColorFactor;
    material.setAlphaMode(hidden ? "BLEND" : "OPAQUE");
    material.pbrMetallicRoughness.setBaseColorFactor([r, g, b, hidden ? 0 : 1]);
  }
}

function syncModelControls() {
  $("view-assembled").setAttribute("aria-pressed", String(!modelState.exploded));
  $("view-exploded").setAttribute("aria-pressed", String(modelState.exploded));
  for (const group of Object.keys(LAYER_GROUPS)) {
    $("layer-" + group).setAttribute("aria-pressed", String(!modelState.hidden.has(group)));
  }
}

function setExploded(exploded) {
  const mv = $("twin-viewer").querySelector("model-viewer");
  const src = exploded ? modelState.urls.exploded : modelState.urls.assembled;
  modelState.exploded = exploded;
  syncModelControls();
  if (!mv || !src || mv.getAttribute("src") === src) return;
  $("result-3d-status").textContent = "LOADING 3D MODEL…";
  $("result-3d-status").hidden = false;
  mv.setAttribute("src", src);
}

function initModelControls() {
  $("view-assembled").addEventListener("click", () => setExploded(false));
  $("view-exploded").addEventListener("click", () => setExploded(true));
  for (const group of Object.keys(LAYER_GROUPS)) {
    $("layer-" + group).addEventListener("click", () => {
      if (modelState.hidden.has(group)) modelState.hidden.delete(group);
      else modelState.hidden.add(group);
      syncModelControls();
      applyLayers($("twin-viewer").querySelector("model-viewer"));
    });
  }
}

async function show3d(data) {
  const stage = $("twin-viewer");
  const status = $("result-3d-status");
  stage.innerHTML = "";
  const has3d = Boolean(data.cad_glb_url || data.cad_3d_preview_url);
  modelState.exploded = false;
  modelState.hidden.clear();
  modelState.urls = { assembled: data.cad_glb_url, exploded: data.cad_glb_exploded_url };
  syncModelControls();
  $("view-exploded").hidden = !data.cad_glb_exploded_url;
  $("model-controls").hidden = true;
  $("model-legend").hidden = true;
  $("tab-3d").hidden = !has3d;
  selectTab(has3d ? $("tab-3d") : $("tab-photo"));
  if (!has3d) return;

  status.textContent = "LOADING 3D MODEL…";
  status.hidden = false;
  try {
    if (!data.cad_glb_url) throw new Error("no GLB");
    modelViewerLoad ??= import("/static/vendor/model-viewer.min.js");
    await modelViewerLoad;
    const mv = document.createElement("model-viewer");
    mv.setAttribute("src", data.cad_glb_url);
    mv.setAttribute("alt", `3D model of the ${TYPE_LABELS[data.sofa_type] || "sofa"} at the quoted size`);
    mv.setAttribute("camera-controls", "");
    mv.setAttribute("touch-action", "pan-y");
    mv.setAttribute("auto-rotate", "");
    mv.setAttribute("auto-rotate-delay", "2500");
    mv.setAttribute("rotation-per-second", "14deg");
    mv.setAttribute("shadow-intensity", "0.9");
    mv.setAttribute("exposure", "1.05");
    mv.setAttribute("camera-orbit", "30deg 72deg auto");
    mv.setAttribute("interaction-prompt", "none");
    mv.addEventListener("load", () => {
      status.hidden = true;
      applyLayers(mv);
      $("model-controls").hidden = false;
      $("model-legend").hidden = false;
    });
    mv.addEventListener("error", () => { status.textContent = "THE 3D MODEL COULDN'T BE DISPLAYED"; });
    stage.appendChild(mv);
  } catch (err) {
    console.warn("3D viewer unavailable:", err);
    if (data.cad_3d_preview_url) {
      stage.innerHTML = `<img src="${esc(data.cad_3d_preview_url)}" alt="3D preview of the sofa">`;
      status.hidden = true;
      $("media-fullscreen").hidden = true;
    } else {
      status.textContent = "THE 3D MODEL COULDN'T BE DISPLAYED";
    }
  }
}

// ── Results ──────────────────────────────────────────────────────────────────
export function renderResults(data) {
  const sa = data.sofa_analysis || {};
  $("detected-type").textContent = TYPE_LABELS[sa.predicted_type] || sa.predicted_type || "SOFA";
  const conf = Math.round((sa.type_confidence ?? sa.confidence ?? 0) * 100);
  $("conf-label").textContent = conf + "%";
  $("conf-fill").style.width = "0";
  setTimeout(() => { $("conf-fill").style.width = conf + "%"; }, 150);
  $("detected-meta").textContent =
    `REQUEST ${data.request_id || "—"} · ${sa.type_source === "classifier" ? "TYPE CLASSIFIER" : "DETECTOR"} · ${sa.detector_backend || "YOLOv8"}`;

  const mismatch = data.type_mismatch;
  const note = $("type-mismatch");
  note.hidden = !mismatch;
  note.textContent = mismatch
    ? `Priced as ${TYPE_LABELS[mismatch.selected] || mismatch.selected} (your selection). The photo check suggested ${TYPE_LABELS[mismatch.detected] || mismatch.detected} — worth a quick double-check. If your selection is right, ignore this.`
    : "";

  // Detected parts
  const grouped = {};
  (Array.isArray(sa.components) ? sa.components : []).forEach(c => {
    const key = c.class_name || "component";
    grouped[key] ??= { count: 0, confidence: 0 };
    grouped[key].count++;
    grouped[key].confidence = Math.max(grouped[key].confidence, Number(c.confidence || 0));
  });
  const entries = Object.entries(grouped);
  $("component-inspection").innerHTML = entries.length ? `
    <div class="component-heading"><span>DETECTED PARTS</span><b>${String(entries.length).padStart(2, "0")} TYPES</b></div>
    <ul class="component-list">
      ${entries.map(([name, info], i) => `
        <li class="component-row">
          <span class="component-number">${String(i + 1).padStart(2, "0")}</span>
          <span class="component-name">${esc(COMPONENT_NAMES[name] || name.replaceAll("_", " ").toUpperCase())}</span>
          <span class="component-count">${info.count > 1 ? "×" + info.count : ""}</span>
          <span class="component-confidence">${Math.round(info.confidence * 100)}%</span>
        </li>`).join("")}
    </ul>` : `<div class="component-heading"><span>DETECTED PARTS</span><b>NONE</b></div>`;

  // Annotated photo (toggle, never replace, so #annotated-img survives)
  const img = $("annotated-img");
  const has = Boolean(data.annotated_image_url);
  if (has) img.src = data.annotated_image_url; else img.removeAttribute("src");
  img.hidden = !has;
  $("annotated-empty").hidden = has;
  $("photo-enlarge").hidden = !has;

  // Dimensions (API: length = overall width, width = depth)
  const d = data.dimensions_mm || {};
  [["r-length", d.length], ["r-width", d.width], ["r-height", d.height],
   ["fp-length", d.length], ["fp-width", d.width], ["fp-height", d.height]]
    .forEach(([id, v]) => { $(id).textContent = mm(v); });

  const q = data.quote || {};
  $("final-price").textContent = "₹" + fmt(q.final_quotation_price);
  $("pdf-btn").href = data.pdf_url || `/api/quotes/${encodeURIComponent(data.request_id)}/pdf`;

  $("bom-tbody").innerHTML = (data.bom || []).map(row => {
    const wastage = Number(row.wastage_pct || 0);
    const net = row.net_qty ?? row.qty;
    return `
    <tr>
      <th scope="row">${esc(row.component)}${row.grade ? ` <small>${esc(gradeLabel(q, row))}</small>` : ""}</th>
      <td>${esc(row.qty)} <small>${esc(row.unit || "")}</small></td>
      <td>${wastage ? `+${wastage}% <small>(net ${esc(net)})</small>` : "—"}</td>
      <td>₹${fmt(row.unit_cost)}</td>
      <td>₹${fmt(row.total_cost)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="5">No BOM rows returned.</td></tr>`;

  const pct = v => (v === undefined || v === null ? "" : ` (${Number(v)}%)`);
  const costRows = [
    ["Materials", q.material_cost], ["Labour", q.labor_cost], ["Finishing", q.finishing_cost],
    ["Subtotal", q.subtotal], [`Overhead${pct(q.overhead_pct)}`, q.overhead],
    ["Cost + overhead", q.cost_after_overhead], [`Profit${pct(q.profit_pct)}`, q.profit],
  ];
  const rowsHtml = rows => rows.map(([k, v]) => `<div><span>${esc(k)}</span><b>₹${fmt(v)}</b></div>`).join("");
  $("quote-rows").innerHTML = rowsHtml(costRows);

  // Retail equivalent (quotes saved before it existed don't have it)
  const hasRetail = q.retail_price_incl_gst !== undefined && q.retail_price_incl_gst !== null;
  $("retail-label").hidden = !hasRetail;
  $("retail-estimate").hidden = !hasRetail;
  $("retail-rows").innerHTML = hasRetail ? rowsHtml([
    ["Factory price", q.final_quotation_price],
    [`Dealer markup${pct(q.dealer_markup_pct)}`, q.retail_price_excl_gst - q.final_quotation_price],
    [`GST${pct(q.gst_pct)}`, q.retail_gst],
    ["Showroom price incl. GST", q.retail_price_incl_gst],
  ]) : "";
  if (hasRetail) {
    $("retail-estimate").textContent = `≈ ₹${fmt(q.retail_price_incl_gst)} in a showroom, incl. ${Number(q.gst_pct)}% GST`;
  }
  const materials = q.fabric_grade_label ? `${q.fabric_grade_label} · ${q.foam_grade_label}. ` : "";
  $("quote-terms").textContent = `${materials}The factory price excludes GST. The retail equivalent is an estimate of what a showroom would charge for the same sofa. Order quantities include a cutting allowance.`;

  showSizeOptions(data);

  const cad = [];
  if (data.cad_step_url)    cad.push(`<a href="${esc(data.cad_step_url)}" download>STEP / 3D CAD ↗</a>`);
  if (data.cad_glb_url)     cad.push(`<a href="${esc(data.cad_glb_url)}" download>GLB / 3D MODEL ↗</a>`);
  if (data.cad_dxf_url)     cad.push(`<a href="${esc(data.cad_dxf_url)}" download>DXF / TECHNICAL DRAWING ↗</a>`);
  if (data.cad_preview_url) cad.push(`<a href="${esc(data.cad_preview_url)}" download>PNG / DRAWING ↗</a>`);
  $("cad-files").innerHTML = cad.length ? cad.join("") : "<span>CAD output was not generated for this request.</span>";

  const path = data.request_id ? `outputs/requests/${data.request_id}/input_request.json` : "—";
  $("fp-path").textContent = path;
  $("fp-copy-btn").onclick = async () => {
    try {
      await navigator.clipboard.writeText(path);
      $("fp-copy-btn").textContent = "COPIED";
      setTimeout(() => { $("fp-copy-btn").textContent = "COPY PATH"; }, 1500);
    } catch { $("fp-copy-btn").textContent = "COPY FAILED"; }
  };

  show3d(data);
}

function gradeLabel(q, row) {
  const name = String(row.component || "").toLowerCase();
  return name.includes("fabric") ? q.fabric_grade_label || row.grade
       : name.includes("foam") ? q.foam_grade_label || row.grade
       : row.grade;
}

// ── Price vs size: +/- 100 mm on each dimension ──────────────────────────────
let sizeRequest = 0;

async function showSizeOptions(data) {
  const body = $("size-tbody");
  const d = data.dimensions_mm || {};
  const q = data.quote || {};
  const mine = ++sizeRequest;   // ignore late replies from an earlier quote
  body.innerHTML = `<tr><td colspan="4">Calculating…</td></tr>`;
  try {
    const res = await getSizeOptions({
      sofaType: data.sofa_type, width: d.length, depth: d.width, height: d.height,
      fabricGrade: q.fabric_grade, foamGrade: q.foam_grade,
    });
    if (mine !== sizeRequest) return;
    const row = (label, w, dd, h, price, diff, reason, current = false) => `
      <tr class="${current ? "is-current" : ""}">
        <th scope="row">${esc(label)}</th>
        <td>${mm(w)} × ${mm(dd)} × ${mm(h)}</td>
        <td>${price === null ? `<small>${esc(reason ? "Outside this type's range" : "—")}</small>` : `₹${fmt(price)}`}</td>
        <td>${diff === null ? "" : current ? "—" : `<span class="${diff > 0 ? "up" : "down"}">${diff > 0 ? "+" : "−"}₹${fmt(Math.abs(diff))}</span>`}</td>
      </tr>`;
    body.innerHTML = row("This size", d.length, d.width, d.height, res.base_price, 0, null, true)
      + res.options.map(o => row(o.label, o.width, o.depth, o.height, o.price, o.difference, o.reason)).join("");
  } catch (err) {
    if (mine === sizeRequest) body.innerHTML = `<tr><td colspan="4">${esc(err.message)}</td></tr>`;
  }
}

// ── Errors and rejections ────────────────────────────────────────────────────
const ERROR_TITLES = {
  rejected:  ["SOFA", "NOT FOUND."],
  input:     ["INPUT", "REVIEW."],
  too_large: ["PHOTO", "TOO LARGE."],
  timeout:   ["TAKING", "TOO LONG."],
  network:   ["SERVER", "UNREACHABLE."],
  server:    ["SOMETHING", "BROKE."],
};

export function renderError(err) {
  const [a, b] = ERROR_TITLES[err.kind] || ERROR_TITLES.server;
  $("reject-title").innerHTML = `${a}<br><em>${b}</em>`;
  $("reject-reason").textContent = err.message;
  const sa = err.data?.sofa_analysis || {};
  $("reject-detail").innerHTML = err.kind === "rejected" && sa.predicted_type
    ? `DETECTED: <strong>${esc(TYPE_LABELS[sa.predicted_type] || sa.predicted_type)}</strong> · CONFIDENCE: <strong>${Math.round((sa.confidence || 0) * 100)}%</strong>`
    : err.kind === "rejected" ? "Tip: use a photo with the whole sofa in frame, taken from the front." : "";
}
