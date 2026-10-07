// Talks to the FastAPI backend. Every failure becomes an ApiError with a
// `kind` the UI can turn into a clear message.

const QUOTE_TIMEOUT_MS = 180_000;   // CAD + 3D generation can take a while on CPU

export class ApiError extends Error {
  constructor(kind, message, data = {}) {
    super(message);
    this.kind = kind;       // timeout | network | too_large | input | rejected | forbidden | not_found | server
    this.data = data;
  }
}

async function readJson(resp) {
  try { return await resp.json(); } catch { return null; }
}

async function request(url, options = {}, timeoutMs = 20_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let resp;
  try {
    resp = await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new ApiError("timeout", "The server took too long to respond. It may be busy — please try again in a minute.");
    }
    throw new ApiError("network", "Can't reach the Stallion server. Check that it is running and that you are on the right network.");
  } finally {
    clearTimeout(timer);
  }

  const data = await readJson(resp);
  if (resp.ok) {
    if (data === null) throw new ApiError("server", `Unexpected reply from the server (HTTP ${resp.status}).`);
    return data;
  }
  const reason = data?.reason;
  switch (resp.status) {
    case 413: throw new ApiError("too_large", reason || "That photo is too large.", data || {});
    case 400: throw new ApiError("input", reason || "Some of the details aren't valid.", data || {});
    case 422: throw new ApiError("input", "Some required details are missing. Please check the form.", data || {});
    case 403: throw new ApiError("forbidden", reason || "Not allowed.", data || {});
    case 404: throw new ApiError("not_found", reason || "Not found.", data || {});
    default:  throw new ApiError("server", `The server hit an error (HTTP ${resp.status}). Please try again; if it keeps happening, check the server log.`, data || {});
  }
}

export function getConfig() {
  return request("/api/config");
}

export async function postQuote(formData) {
  const data = await request("/api/quote", { method: "POST", body: formData }, QUOTE_TIMEOUT_MS);
  if (data.status === "rejected") throw new ApiError("rejected", data.reason || "No sofa was found in the photo.", data);
  return data;
}

export async function getProgress(progressId) {
  try { return await request(`/api/progress/${encodeURIComponent(progressId)}`, {}, 5_000); }
  catch { return null; }   // progress is best-effort; never fail the quote over it
}

export function listQuotes(staffKey) {
  return request("/api/quotes", { headers: staffKey ? { "X-Staff-Key": staffKey } : {} });
}

export function getQuote(requestId) {
  return request(`/api/quotes/${encodeURIComponent(requestId)}`);
}

export function getSizeOptions({ sofaType, width, depth, height, fabricGrade, foamGrade }) {
  const q = new URLSearchParams({
    sofa_type: sofaType, width, depth, height,
    fabric_grade: fabricGrade || "standard", foam_grade: foamGrade || "standard",
  });
  return request(`/api/size-options?${q}`);
}

export function getPricing(staffKey) {
  return request("/api/pricing", { headers: staffKey ? { "X-Staff-Key": staffKey } : {} });
}

export function savePricing(staffKey, sheet) {
  return request("/api/pricing", {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(staffKey ? { "X-Staff-Key": staffKey } : {}) },
    body: JSON.stringify(sheet),
  });
}
