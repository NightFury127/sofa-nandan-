// Small shared helpers.

export const $ = id => document.getElementById(id);

export const TYPE_LABELS = {
  "1_seater": "1-SEATER / ARMCHAIR",
  "2_seater": "2-SEATER",
  "3_seater": "3-SEATER",
  "4_seater_plus": "4-SEATER",
  "l_shape": "L-SHAPE",
};

export function fmt(n) {
  if (n === undefined || n === null || n === "") return "—";
  return Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function mm(n) {
  return n === undefined || n === null || n === "" ? "—" : Number(n).toLocaleString("en-IN");
}

export function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m]));
}

// Session storage can throw (private mode, blocked storage); never let it break the page.
export const session = {
  get(key) { try { return sessionStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { sessionStorage.setItem(key, value); } catch { /* unavailable */ } },
  remove(key) { try { sessionStorage.removeItem(key); } catch { /* unavailable */ } },
};
