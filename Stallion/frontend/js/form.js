// Project input: photo upload, sofa type picker, dimensions with per-type
// range checks (limits come from /api/config, i.e. master_dimensions.csv).
import { $, esc } from "./util.js";

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

  // ── Photo ──────────────────────────────────────────────────────────────────
  const photoError = $("photo-error");
  const setPhotoError = msg => { photoError.textContent = msg || ""; photoError.hidden = !msg; };

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
    update();
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
  function selectType(btn, focus = false) {
    selectedType = btn.dataset.type;
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
  }
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
    $(f.input).addEventListener("input", () => update(false));
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
