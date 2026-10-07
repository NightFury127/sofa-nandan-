// Staff rate editor: material rates and wastage, fabric/foam grades, labour
// and finishing per sofa type, overhead and profit. Saves the whole sheet; the
// server validates it and keeps the previous version.
import { $, esc, TYPE_LABELS } from "./util.js";

const GROUP_LABELS = { fabric: "Fabric grades", foam: "Foam grades" };

function num(name, value, { step = "any", min = 0, max = null, suffix = "" } = {}) {
  return `<span class="rate-input"><input type="number" name="${esc(name)}" value="${esc(value)}" step="${step}" min="${min}"${max !== null ? ` max="${max}"` : ""} inputmode="decimal" required>${suffix ? `<i>${suffix}</i>` : ""}</span>`;
}

export function renderRates(sheet) {
  const form = $("rates-form");
  const updated = sheet.updated_at ? new Date(sheet.updated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—";
  const materials = Object.entries(sheet.materials);

  form.innerHTML = `
    <p class="rates-meta">Last saved ${esc(updated)}. Prices are exclusive of GST.</p>

    <h3>Materials</h3>
    <table class="rates-table">
      <thead><tr><th scope="col">Material</th><th scope="col">Rate (₹ per unit)</th><th scope="col">Wastage</th></tr></thead>
      <tbody>${materials.map(([name, m]) => `
        <tr><th scope="row">${esc(name)}<small>${esc(m.unit)}${m.grade_group ? ` · ${esc(m.grade_group)} grade applies` : ""}</small></th>
          <td>${num(`mat|${name}|rate`, m.rate, { suffix: "₹" })}</td>
          <td>${num(`mat|${name}|wastage_pct`, m.wastage_pct, { max: 100, suffix: "%" })}</td></tr>`).join("")}
      </tbody>
    </table>

    ${Object.entries(sheet.grades).map(([group, options]) => `
      <h3>${esc(GROUP_LABELS[group] || group)}</h3>
      <table class="rates-table">
        <thead><tr><th scope="col">Option</th><th scope="col">Rate × multiplier</th></tr></thead>
        <tbody>${Object.entries(options).map(([key, g]) => `
          <tr><th scope="row"><input class="rate-label" name="grade|${esc(group)}|${esc(key)}|label" value="${esc(g.label)}" aria-label="${esc(group)} grade ${esc(key)} name"><small>${esc(key)}</small></th>
            <td>${num(`grade|${group}|${key}|multiplier`, g.multiplier, { min: 0.05, max: 20, suffix: "×" })}</td></tr>`).join("")}
        </tbody>
      </table>`).join("")}

    <h3>Labour and finishing per sofa</h3>
    <table class="rates-table">
      <thead><tr><th scope="col">Sofa type</th><th scope="col">Labour</th><th scope="col">Finishing</th></tr></thead>
      <tbody>${Object.keys(sheet.labour_by_type).map(t => `
        <tr><th scope="row">${esc(TYPE_LABELS[t] || t)}</th>
          <td>${num(`labour|${t}`, sheet.labour_by_type[t], { suffix: "₹" })}</td>
          <td>${num(`finishing|${t}`, sheet.finishing_by_type[t], { suffix: "₹" })}</td></tr>`).join("")}
      </tbody>
    </table>

    <h3>Margins</h3>
    <table class="rates-table">
      <tbody>
        <tr><th scope="row">Overhead<small>on materials + labour + finishing</small></th><td>${num("overhead_pct", sheet.overhead_pct, { max: 200, suffix: "%" })}</td></tr>
        <tr><th scope="row">Profit<small>on cost + overhead</small></th><td>${num("profit_pct", sheet.profit_pct, { max: 200, suffix: "%" })}</td></tr>
      </tbody>
    </table>

    <label class="rates-note">Note shown to staff<textarea name="note" rows="2" maxlength="300">${esc(sheet.note || "")}</textarea></label>

    <div class="rates-actions">
      <button type="submit" class="pdf-button">SAVE RATES</button>
      <button type="button" class="outline-button" id="rates-discard">DISCARD CHANGES</button>
    </div>
    <p class="rates-status" id="rates-status" role="status"></p>`;
}

// Read the form back into a full rate sheet (starting from the loaded one).
export function readRates(sheet) {
  const out = structuredClone(sheet);
  const form = $("rates-form");
  for (const el of form.querySelectorAll("input[name], textarea[name]")) {
    const parts = el.name.split("|");
    const value = el.type === "number" ? Number(el.value) : el.value;
    if (parts[0] === "mat") out.materials[parts[1]][parts[2]] = value;
    else if (parts[0] === "grade") out.grades[parts[1]][parts[2]][parts[3]] = value;
    else if (parts[0] === "labour") out.labour_by_type[parts[1]] = value;
    else if (parts[0] === "finishing") out.finishing_by_type[parts[1]] = value;
    else out[parts[0]] = value;
  }
  return out;
}
