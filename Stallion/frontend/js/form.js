// Project input: photo upload, sofa type picker, dimensions with per-type
// range checks (limits come from /api/config, i.e. master_dimensions.csv).
// Choosing a photo runs type detection: a confident result pre-selects the
// type (the customer can still change it), and a live 3D model of the chosen
// type follows the dimensions as they are typed.
import { $, esc, TYPE_LABELS } from "./util.js";
import { detectType, modelPreviewUrl } from "./api.js";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

// UI field -> API form field. The UI uses furniture terms (W x D x H);
// the API calls the overall width "length_mm" and the depth "width_mm".
const FIELDS = [
  { key: "width",  input: "length-input", api: "length_mm" },
  { key: "depth",  input: "width-input",  api: "width_mm" },
  { key: "height", input: "height-input", api: "height_mm" },
];

export function initForm({ config, onSubmit }) {
  const form = $("project-form");
  const submitBtn = $("submit-btn");
  const imageInput = $("image-input");
  const uploadZone = $("upload-zone");
  const typeButtons = [...document.querySelectorAll(".sofa-type")];
  const limits = config?.types || {};
  const maxMb = config?.max_upload_mb || 15;

  let file = null;
  let selectedType = null;
  let detected = null;      // last detection result for the current photo
  let userPicked = false;   // the customer chose a type themselves for this photo
  let detectRun = 0;        // ignores answers for a photo that was since replaced

  // ── Photo ──────────────────────────────────────────────────────────────────
  const photoError = $("photo-error");
  const setPhotoError = msg => { photoError.textContent = msg || ""; photoError.hidden = !msg; };

  const note = $("detect-note");
  function setNote(html, warning = false) {
    note.innerHTML = html || "";
    note.hidden = !html;
    note.classList.toggle("is-warning", warning);
  }
  const label = t => esc(TYPE_LABELS[t] || t);

  async function runDetection(f) {
    const run = ++detectRun;
    detected = null;
    setNote("Recognising the sofa type…");
    let result;
    try {
      result = await detectType(f);
    } catch {
      if (run === detectRun) setNote("We couldn't recognise the type automatically. Please choose it below.", true);
      return;
    }
    if (run !== detectRun) return;
    detected = result;
    if (!result.sofa_found) {
      setNote("We couldn't find a sofa in this photo. Try a clearer photo of the whole sofa, or the quote will be rejected.", true);
      return;
    }
    const pct = result.confidence != null ? ` (${Math.round(result.confidence * 100)}% sure)` : "";
    const btn = typeButtons.find(b => b.dataset.type === result.sofa_type);
    if (result.confident && btn) {
      if (!userPicked) selectType(btn, false, "detect");
      describeChoice();
    } else if (btn) {
      const alt = result.runner_up;
      const or = alt ? ` or a <b>${label(alt.sofa_type)}</b> (${Math.round(alt.confidence * 100)}%)` : "";
      setNote(`This looks like a <b>${label(result.sofa_type)}</b>${pct}${or}, but we're not sure. Please choose the type below.`, true);
    } else {
      setNote("We couldn't tell the sofa type from this photo. Please choose it below.", true);
    }
  }

  // Note under the picker: what was detected, and whether the choice differs
  function describeChoice() {
    if (!detected?.sofa_found || !detected.confident) return;
    const pct = detected.confidence != null ? ` (${Math.round(detected.confidence * 100)}% sure)` : "";
    if (selectedType === detected.sofa_type) {
      setNote(`Detected from your photo: <b>${label(detected.sofa_type)}</b>${pct}. The sizes below are for this type. Not right? Pick another type.`);
    } else if (selectedType) {
      setNote(`Using your choice: <b>${label(selectedType)}</b>. The photo looked like a ${label(detected.sofa_type)}${pct}.`);
    }
  }

  function setFile(f) {
    if (!f) return;
    if (!ACCEPTED.includes(f.type)) { setPhotoError("Please use a JPG, PNG or WEBP photo."); return; }
    if (f.size > maxMb * 1024 * 1024) {
      setPhotoError(`That photo is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${maxMb} MB. A phone photo at normal quality is fine.`);
      return;
    }
    setPhotoError("");
    file = f;
    $("preview-img").src = URL.createObjectURL(f);
    $("preview-stage").classList.add("show");
    $("upload-status").textContent = `Photo selected: ${f.name}`;
    userPicked = false;
    update();
    runDetection(f);
  }

  ["dragover", "dragenter"].forEach(evt => uploadZone.addEventListener(evt, e => {
    e.preventDefault(); uploadZone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach(evt => uploadZone.addEventListener(evt, e => {
    e.preventDefault(); uploadZone.classList.remove("is-dragging");
  }));
  uploadZone.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));
  imageInput.addEventListener("change", () => setFile(imageInput.files[0]));

  // ── Sofa type: a radio group with arrow-key navigation ─────────────────────
  function selectType(btn, focus = false, source = "user") {
    selectedType = btn.dataset.type;
    if (source === "user") userPicked = true;
    typeButtons.forEach(b => {
      const on = b === btn;
      b.classList.toggle("active", on);
      b.setAttribute("aria-checked", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    if (focus) btn.focus();
    $("type-required").hidden = true;
    showRanges();
    update();
    describeChoice();
    showPreview();
  }

  // ── Live 3D preview of the chosen type ────────────────────────────────────
  let modelViewerLoad = null;
  let previewTimer = null;
  let previewSrc = "";

  // The typed size if it's complete and in range, else the type's standard size
  function previewDims() {
    const lim = limits[selectedType];
    const typed = FIELDS.map(f => Number($(f.input).value));
    const inRange = lim && typed.every((v, i) => v >= lim[FIELDS[i].key][0] && v <= lim[FIELDS[i].key][1]);
    return inRange ? { dims: typed, standard: false } : { dims: lim ? lim.base : null, standard: true };
  }

  async function showPreview() {
    const box = $("type-preview");
    const { dims, standard } = previewDims();
    if (!selectedType || !dims) { box.hidden = true; return; }
    box.hidden = false;
    const [w, d, h] = dims;
    $("type-preview-caption").textContent =
      `${TYPE_LABELS[selectedType] || selectedType} · ${w} × ${d} × ${h} MM${standard ? " (STANDARD SIZE)" : ""} · DRAG TO ROTATE`;
    const src = modelPreviewUrl(selectedType, w, d, h);
    if (src === previewSrc) return;
    previewSrc = src;
    try {
      modelViewerLoad ??= import("/static/vendor/model-viewer.min.js");
      await modelViewerLoad;
    } catch {
      box.hidden = true;   // 3D not available in this browser; the form still works
      return;
    }
    let mv = $("type-preview-stage").querySelector("model-viewer");
    if (!mv) {
      mv = document.createElement("model-viewer");
      mv.setAttribute("camera-controls", "");
      mv.setAttribute("touch-action", "pan-y");
      mv.setAttribute("shadow-intensity", "0.8");
      mv.setAttribute("camera-orbit", "30deg 72deg auto");
      mv.setAttribute("interaction-prompt", "none");
      $("type-preview-stage").appendChild(mv);
    }
    mv.setAttribute("alt", `3D model of a ${TYPE_LABELS[selectedType] || "sofa"}`);
    mv.setAttribute("src", src);
  }
  const schedulePreview = () => { clearTimeout(previewTimer); previewTimer = setTimeout(showPreview, 450); };
  typeButtons.forEach((btn, i) => {
    btn.tabIndex = i === 0 ? 0 : -1;
    btn.addEventListener("click", () => selectType(btn));
    btn.addEventListener("keydown", e => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (step) {
        e.preventDefault();
        selectType(typeButtons[(i + step + typeButtons.length) % typeButtons.length], true);
      } else if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        selectType(btn);
      }
    });
  });

  // ── Fabric / foam grades (from the rate sheet) ────────────────────────────
  const grades = config?.grades || {};
  document.querySelectorAll(".grade-options").forEach(box => {
    const group = box.dataset.group;
    const options = grades[group] || [{ key: "standard", label: "Standard" }];
    box.innerHTML = options.map(o => `
      <label class="grade-option">
        <input type="radio" name="${esc(group)}_grade" value="${esc(o.key)}" ${o.key === "standard" ? "checked" : ""}>
        <span>${esc(o.label)}</span>
      </label>`).join("");
  });
  const gradeValue = group => form.querySelector(`input[name="${group}_grade"]:checked`)?.value || "standard";

  // ── Dimensions ────────────────────────────────────────────────────────────
  function showRanges() {
    const lim = limits[selectedType];
    FIELDS.forEach(f => {
      const hint = $(`${f.key}-hint`);
      const input = $(f.input);
      if (lim) {
        const [lo, hi] = lim[f.key];
        hint.textContent = `${lo}–${hi} mm`;
        input.min = lo; input.max = hi;
        if (!input.value) input.placeholder = String(lim.base[FIELDS.indexOf(f)]);
      } else {
        hint.textContent = "Pick a type to see the range";
      }
    });
  }

  // Returns true when every dimension is filled and inside the type's range.
  function checkDimensions(showErrors) {
    const lim = limits[selectedType];
    let ok = true;
    FIELDS.forEach(f => {
      const input = $(f.input);
      const err = $(`${f.key}-error`);
      const v = Number(input.value);
      let msg = "";
      if (!input.value) ok = false;
      else if (!(v > 0)) { msg = "Enter a positive number."; ok = false; }
      else if (lim) {
        const [lo, hi] = lim[f.key];
        if (v < lo || v > hi) { msg = `Must be ${lo}–${hi} mm for this type.`; ok = false; }
      }
      const show = showErrors && msg;
      err.textContent = show ? msg : "";
      err.hidden = !show;
      input.setAttribute("aria-invalid", show ? "true" : "false");
    });
    return ok;
  }

  function update(showErrors = false) {
    const dimsOk = checkDimensions(showErrors);
    submitBtn.disabled = !(file && selectedType && dimsOk);
    const missing = [!file && "a photo", !selectedType && "a sofa type", !dimsOk && "valid dimensions"].filter(Boolean);
    $("submit-hint").textContent = missing.length ? `Still needed: ${missing.join(", ")}.` : "Ready to generate.";
  }

  FIELDS.forEach(f => {
    $(f.input).addEventListener("input", () => { update(false); schedulePreview(); });
    $(f.input).addEventListener("blur", () => update(true));
  });

  form.addEventListener("submit", e => {
    e.preventDefault();
    update(true);
    if (submitBtn.disabled) return;
    const fd = new FormData();
    fd.append("image", file);
    fd.append("customer_name", $("customer-input").value.trim() || "Guest");
    FIELDS.forEach(f => fd.append(f.api, $(f.input).value));
    fd.append("sofa_type", selectedType);
    fd.append("fabric_grade", gradeValue("fabric"));
    fd.append("foam_grade", gradeValue("foam"));
    onSubmit(fd);
  });

  showRanges();
  update();

  return {
    reset() {
      file = null;
      selectedType = null;
      detected = null;
      userPicked = false;
      detectRun++;
      setNote("");
      clearTimeout(previewTimer);
      $("type-preview").hidden = true;
      imageInput.value = "";
      $("preview-stage").classList.remove("show");
      $("upload-status").textContent = "";
      setPhotoError("");
      typeButtons.forEach((b, i) => {
        b.classList.remove("active"); b.setAttribute("aria-checked", "false"); b.tabIndex = i === 0 ? 0 : -1;
      });
      $("type-required").hidden = false;
      FIELDS.forEach(f => { $(f.input).value = ""; });
      $("customer-input").value = "";
      form.querySelectorAll('.grade-options input[value="standard"]').forEach(r => { r.checked = true; });
      showRanges();
      update();
    },
  };
}
