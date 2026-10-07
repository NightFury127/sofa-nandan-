"""
FastAPI backend for the Stallion Sofa Costing Engine.

Wraps the existing Phase 1-3 pipeline as REST endpoints so the
web frontend can call it without touching any pipeline code.

Endpoints:
  GET  /                        → serve frontend/index.html
  POST /api/quote               → run the full pipeline, return JSON
  GET  /api/config              → sofa types and their allowed dimensions
  GET  /api/progress/{id}       → current pipeline step for a running quote
  GET  /api/quotes              → past quotes (staff only, see _staff_allowed)
  GET  /api/quotes/{id}         → one saved quote (the id is the secret)
  GET  /api/quotes/{id}/pdf     → branded quotation PDF
  GET  /outputs/...             → serve output files (annotated image, etc.)
  GET  /static/...              → serve frontend assets

Run:
  python -m uvicorn api:app --reload --port 8000
"""

import os
import re
import sys
import mimetypes
import csv
import json
import time
import shutil
import secrets
import threading
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Path setup — api.py lives in src/, pipeline modules are siblings
# ---------------------------------------------------------------------------

SRC_DIR     = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
FRONTEND_DIR = PROJECT_ROOT / "frontend"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"

sys.path.insert(0, str(SRC_DIR))

from image_processor        import process_image, ImageValidationError
from sofa_validator         import validate_sofa, SofaValidationError, TYPE_CONFIDENCE_THRESHOLD
from cost_engine            import SofaCostEngine, normalize_sofa_type
from cad_generator          import SofaCADGenerator
from cad_generator_3d       import build_sofa_mesh, export_3d_model, render_preview_image
from production_cad         import build_sofa_step_model
from dimension_estimator_api import add_dimension_estimates_to_response
from quote_pdf              import build_quote_pdf
from pricing                import load_pricing, save_pricing, PricingError
from fastapi                import Body

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Stallion Sofa Costing Engine", version="1.0.0")

# The frontend is served from this same app, so no cross-origin access is
# needed by default. For a separately hosted frontend, set e.g.
#   STALLION_ALLOWED_ORIGINS=https://quotes.example.edu,http://localhost:5500
_allowed_origins = [o.strip() for o in os.environ.get("STALLION_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

# Windows' mimetypes table lacks these, so StaticFiles would send text/plain
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("model/step", ".step")
mimetypes.add_type("image/vnd.dxf", ".dxf")

# Serve output files (annotated images, CSVs, etc.)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

class NoCacheStaticFiles(StaticFiles):
    """
    StaticFiles that makes browsers revalidate on every load ("no-cache" still
    allows caching; unchanged files come back as a cheap 304). Without it,
    browsers keep serving stale frontend files after an update — and the ES
    modules in frontend/js/ import each other, so a ?v= query on the entry
    script alone would not refresh them.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Serve frontend static assets
app.mount("/static", NoCacheStaticFiles(directory=str(FRONTEND_DIR)), name="static")


(OUTPUTS_DIR / "cad").mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helper: read a CSV file into a list of dicts, coercing numeric strings
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list:
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            clean = {}
            for k, v in row.items():
                if k is None:
                    continue
                try:
                    clean[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    clean[k] = v
            rows.append(clean)
    return rows


def _next_request_id() -> str:
    """
    web_YYYYMMDD_HHMMSS_<16 hex>. The random suffix keeps concurrent requests
    apart and makes output URLs (which expose customer photos and quotes)
    impractical to guess.
    """
    return f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(8)}"


REQUEST_ID_RE = re.compile(r"^web_\d{8}_\d{6}_[0-9a-f]{16}$")


def _quote_folder(request_id: str):
    """Folder of a saved quote, or None. Validates the id (no path tricks)."""
    if not REQUEST_ID_RE.match(request_id):
        return None
    folder = OUTPUTS_DIR / "requests" / request_id
    return folder if (folder / "response.json").exists() else None


# ---------------------------------------------------------------------------
# Progress: the frontend sends a random progress_id with its quote request and
# polls /api/progress/{id} while the pipeline runs (in a worker thread).
# ---------------------------------------------------------------------------

PROGRESS_STEPS = [
    ("upload",    "Receiving the photo"),
    ("image",     "Checking the image"),
    ("detect",    "Detecting the sofa and its parts"),
    ("cost",      "Scaling the bill of materials and pricing"),
    ("drawing",   "Drawing the technical views"),
    ("model3d",   "Building the 3D model"),
    ("step",      "Writing the CAD (STEP) file"),
    ("done",      "Done"),
]
PROGRESS_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_progress: dict = {}
_progress_lock = threading.Lock()


def _set_progress(progress_id, step: str):
    if not progress_id:
        return
    index = [s for s, _ in PROGRESS_STEPS].index(step)
    with _progress_lock:
        _progress[progress_id] = {
            "step": step, "label": PROGRESS_STEPS[index][1],
            "index": index, "total": len(PROGRESS_STEPS) - 1, "t": time.time(),
        }
        # Forget entries older than 10 minutes so the dict can't grow forever
        cutoff = time.time() - 600
        for pid in [p for p, v in _progress.items() if v["t"] < cutoff]:
            del _progress[pid]


# ---------------------------------------------------------------------------
# Staff access (quote history): listing every quote would undo the
# unguessable-id protection, so it is restricted.
#   - STALLION_STAFF_KEY set   → requests must send header X-Staff-Key: <key>
#   - STALLION_STAFF_KEY unset → only requests from this machine (localhost)
# Behind a reverse proxy every request looks local, so set the key there.
# ---------------------------------------------------------------------------

def _staff_allowed(request: Request, staff_key) -> bool:
    expected = os.environ.get("STALLION_STAFF_KEY")
    if expected:
        return bool(staff_key) and secrets.compare_digest(staff_key, expected)
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost")


def _type_limits() -> dict:
    """Allowed dimensions per sofa type, from master_dimensions.csv."""
    path = PROJECT_ROOT / "data" / "master_template" / "master_dimensions.csv"
    to_ui = {"1-seater": "1_seater", "2-seater": "2_seater", "3-seater": "3_seater",
             "4-seater": "4_seater_plus", "l-shape": "l_shape"}
    limits = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = to_ui.get(row["variant"].strip().lower())
            if key:
                limits[key] = {
                    # UI names: width = overall length, depth = front-to-back
                    "width":  [float(row["min_length"]), float(row["max_length"])],
                    "depth":  [float(row["min_width"]),  float(row["max_width"])],
                    "height": [float(row["min_height"]), float(row["max_height"])],
                    "base":   [float(row["base_length"]), float(row["base_width"]), float(row["base_height"])],
                }
    return limits


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def serve_index():
    """Serve the single-page frontend."""
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/config")
def get_config():
    """Sofa types, allowed dimensions, fabric/foam grades and upload limits, for the form."""
    grades = load_pricing()["grades"]
    return {
        "types": _type_limits(),
        "grades": {group: [{"key": k, "label": g["label"]} for k, g in options.items()]
                   for group, options in grades.items()},
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


@app.get("/api/size-options")
def size_options(sofa_type: str, width: float, depth: float, height: float,
                 fabric_grade: str = "standard", foam_grade: str = "standard", step: float = 100):
    """
    Price at the quoted size and at +/- `step` mm on each dimension, so an
    undecided customer can see what a size change costs. Sizes outside the
    type's allowed range come back with price None and a reason.
    """
    engine = SofaCostEngine()
    engine.load_data()
    step = max(10.0, min(float(step), 500.0))

    def price(w, d, h):
        try:
            return round(engine.estimate_price(w, d, h, sofa_type, fabric_grade, foam_grade), 2), None
        except ValueError as exc:
            return None, str(exc)

    base, err = price(width, depth, height)
    if base is None:
        return JSONResponse({"status": "error", "reason": err}, status_code=400)
    rows = []
    for dim, label in (("width", "Width"), ("depth", "Depth"), ("height", "Height")):
        for sign in (-1, 1):
            dims = {"width": width, "depth": depth, "height": height}
            dims[dim] += sign * step
            p, reason = price(dims["width"], dims["depth"], dims["height"])
            rows.append({
                "dimension": dim, "label": f"{label} {'+' if sign > 0 else '−'}{step:g} mm",
                "width": dims["width"], "depth": dims["depth"], "height": dims["height"],
                "price": p, "difference": None if p is None else round(p - base, 2),
                "reason": reason,
            })
    return {"base_price": base, "step_mm": step, "options": rows}


@app.get("/api/pricing")
def get_pricing(request: Request, x_staff_key: str = Header(None)):
    """The rate sheet, for the staff rate editor."""
    if not _staff_allowed(request, x_staff_key):
        return JSONResponse({"status": "error", "reason": "Staff key required to view rates."}, status_code=403)
    return load_pricing()


@app.put("/api/pricing")
def put_pricing(request: Request, payload: dict = Body(...), x_staff_key: str = Header(None)):
    """Validate and save the rate sheet; the previous version is kept."""
    if not _staff_allowed(request, x_staff_key):
        return JSONResponse({"status": "error", "reason": "Staff key required to change rates."}, status_code=403)
    try:
        return {"status": "saved", "pricing": save_pricing(payload)}
    except PricingError as exc:
        return JSONResponse({"status": "error", "reason": str(exc)}, status_code=400)


@app.get("/api/progress/{progress_id}")
def get_progress(progress_id: str):
    with _progress_lock:
        entry = _progress.get(progress_id)
    if entry is None:
        # Polling can start before the upload reaches the server: not an error
        return {"step": None}
    return {k: v for k, v in entry.items() if k != "t"}


@app.get("/api/quotes")
def list_quotes(request: Request, limit: int = 50,
                x_staff_key: str = Header(None)):
    """Most recent successful quotes, newest first (staff only)."""
    if not _staff_allowed(request, x_staff_key):
        return JSONResponse({"status": "error", "reason": "Staff key required to view quote history."},
                            status_code=403)
    folders = sorted((OUTPUTS_DIR / "requests").glob("web_*/response.json"), reverse=True)
    items = []
    for p in folders[:max(1, min(limit, 500))]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append({
            "request_id":    d.get("request_id"),
            "created_at":    d.get("created_at"),
            "customer_name": d.get("customer_name"),
            "sofa_type":     d.get("sofa_type"),
            "dimensions_mm": d.get("dimensions_mm"),
            "final_price":   (d.get("quote") or {}).get("final_quotation_price"),
        })
    return {"quotes": items}


@app.get("/api/quotes/{request_id}")
def get_quote(request_id: str):
    folder = _quote_folder(request_id)
    if folder is None:
        return JSONResponse({"status": "error", "reason": "Quote not found."}, status_code=404)
    return JSONResponse(json.loads((folder / "response.json").read_text(encoding="utf-8")))


@app.get("/api/quotes/{request_id}/pdf")
def get_quote_pdf(request_id: str):
    folder = _quote_folder(request_id)
    if folder is None:
        return JSONResponse({"status": "error", "reason": "Quote not found."}, status_code=404)
    pdf = build_quote_pdf(folder)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Stallion-quote-{request_id[4:19]}.pdf"'})


# Plain `def` (not async): FastAPI runs it in a worker thread, so the
# CPU-heavy detection / CAD work doesn't block other requests.
@app.post("/api/quote")
def create_quote(
    image:         UploadFile = File(...),
    customer_name: str   = Form("guest"),
    length_mm:     float = Form(...),
    width_mm:      float = Form(...),
    height_mm:     float = Form(...),
    # Required: the user's type is what gets priced. The detected type (from the
    # type classifier, ~95% on held-out catalogue photos and ~81% on held-out
    # room photos; see eval_sofa_types.py)
    # is only used as a cross-check to flag a likely wrong selection.
    sofa_type:     str   = Form(...),
    # Optional random id from the frontend, used to report progress
    progress_id:   str   = Form(None),
    fabric_grade:  str   = Form("standard"),
    foam_grade:    str   = Form("standard"),
):
    """
    Run the Phase 1-3 pipeline on the uploaded image + dimensions.

    Returns a JSON response with:
      status          "success" | "rejected" | "error"
      sofa_analysis   detection results (always present if image was valid)
      bom             list of scaled component rows
      quote           cost breakdown dict
      annotated_image_url   URL to the bbox-annotated image
    """
    if progress_id and not PROGRESS_ID_RE.match(progress_id):
        progress_id = None
    _set_progress(progress_id, "upload")

    content = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"status": "error",
             "reason": f"Image too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."},
            status_code=413,
        )

    request_id     = _next_request_id()
    request_folder = OUTPUTS_DIR / "requests" / request_id
    request_folder.mkdir(parents=True, exist_ok=True)

    # ── Save uploaded image ──────────────────────────────────────────────────
    suffix     = Path(image.filename or "upload.jpg").suffix.lower() or ".jpg"
    image_path = request_folder / f"uploaded_image{suffix}"
    with open(image_path, "wb") as f:
        f.write(content)

    # ── Phase 2: image validation & processing ───────────────────────────────
    _set_progress(progress_id, "image")
    try:
        image_result = process_image(str(image_path), str(request_folder))
    except (FileNotFoundError, ImageValidationError) as exc:
        return JSONResponse(
            {"status": "error", "reason": str(exc)},
            status_code=400,
        )

    # ── Phase 3: sofa type validation (hard gate) ────────────────────────────
    sofa_result   = {}
    annotated_url = None
    _set_progress(progress_id, "detect")

    try:
        sofa_result = validate_sofa(str(image_path), str(request_folder))
        # Convert absolute annotated path → URL
        ann_path = sofa_result.get("annotated_image_path", "")
        if ann_path and Path(ann_path).exists():
            rel = Path(ann_path).relative_to(OUTPUTS_DIR)
            annotated_url = f"/outputs/{rel.as_posix()}"
        # Remove non-serialisable absolute path from response
        sofa_result.pop("annotated_image_path", None)
        sofa_result.pop("analysis_path", None)

    except SofaValidationError as exc:
        # Read sofa_analysis.json for type/confidence details
        analysis_json = request_folder / "sofa_analysis.json"
        if analysis_json.exists():
            with open(analysis_json) as f:
                sofa_result = json.load(f)
        sofa_result.pop("annotated_image_path", None)
        sofa_result.pop("analysis_path", None)

        ann_path = request_folder / "sofa_annotated.jpg"
        if ann_path.exists():
            annotated_url = f"/outputs/requests/{request_id}/sofa_annotated.jpg"

        return JSONResponse({
            "status":         "rejected",
            "reason":         str(exc),
            "request_id":     request_id,
            "sofa_analysis":  sofa_result,
            "annotated_image_url": annotated_url,
        })

    # ── Dimension estimation (non-blocking, adds estimated_dimensions field) ──
    estimated_dimensions = {}
    try:
        enriched = add_dimension_estimates_to_response(
            response={},
            sofa_analysis=sofa_result,
            anchor_length_mm=length_mm,
        )
        estimated_dimensions = enriched.get("estimated_dimensions", {})
    except Exception as exc:
        print(f"[DimEst] Estimation failed (non-fatal): {exc}")

    # ── Price with the user's type; flag it if the detector disagrees ────────
    _set_progress(progress_id, "cost")
    detected_type = sofa_result.get("predicted_type")
    type_mismatch = None
    try:
        type_conf = sofa_result.get("type_confidence")
        confident = type_conf is None or type_conf >= TYPE_CONFIDENCE_THRESHOLD
        if (detected_type and confident
                and normalize_sofa_type(sofa_type) != normalize_sofa_type(detected_type)):
            type_mismatch = {"selected": sofa_type, "detected": detected_type,
                             "detected_confidence": type_conf}

        # ── Phase 1: cost engine ─────────────────────────────────────────────
        engine       = SofaCostEngine()
        quote_result = engine.generate_quote(
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            sofa_type=sofa_type,
            output_prefix=request_id,
            fabric_grade=fabric_grade,
            foam_grade=foam_grade,
        )
    except ValueError as exc:
        # Out-of-range dimensions or unknown sofa type — a client input problem
        return JSONResponse({
            "status":         "error",
            "reason":         str(exc),
            "request_id":     request_id,
            "sofa_analysis":  sofa_result,
            "annotated_image_url": annotated_url,
        }, status_code=400)

    output_files = quote_result.get("output_files", {})

    # Copy BOM + cost CSVs into request folder and read them back as JSON
    bom_rows  = []
    cost_rows = []

    if output_files.get("bom_csv") and Path(output_files["bom_csv"]).exists():
        dst = request_folder / "bom.csv"
        shutil.copy2(output_files["bom_csv"], dst)
        bom_rows = _read_csv(dst)

    if output_files.get("cost_csv") and Path(output_files["cost_csv"]).exists():
        dst = request_folder / "cost.csv"
        shutil.copy2(output_files["cost_csv"], dst)
        cost_rows = _read_csv(dst)

    if output_files.get("summary_json") and Path(output_files["summary_json"]).exists():
        shutil.copy2(output_files["summary_json"], request_folder / "quote_summary.json")

    # Merge BOM scaling info into cost rows (same order, join on component_group)
    bom_by_name = {r.get("component_group", ""): r for r in bom_rows}
    merged_bom  = []
    for row in cost_rows:
        name = row.get("component_group", "")
        bom_info = bom_by_name.get(name, {})
        merged_bom.append({
            "component":    name,
            "scaling_rule": bom_info.get("scaling_rule", "—"),
            "unit":         row.get("unit") or bom_info.get("unit", ""),
            "net_qty":      round(float(row.get("net_qty", row.get("new_qty", 0))), 3),
            "wastage_pct":  float(row.get("wastage_pct", 0) or 0),
            "qty":          round(float(row.get("new_qty", 0)), 3),   # order qty incl. wastage
            "grade":        row.get("grade") or "",
            "unit_cost":    float(row.get("unit_cost", 0)),
            "total_cost":   round(float(row.get("total_cost", 0)), 2),
        })

    # quote summary
    summary = quote_result.get("summary", quote_result)

    # ── Phase 4: CAD generation ──────────────────────────────────────────────
    cad_preview_url = None
    cad_dxf_url     = None
    cad_step_url    = None
    cad_glb_url     = None
    cad_3d_prev_url = None
    cad_error       = None

    _set_progress(progress_id, "drawing")
    try:
        bom_for_cad = {r.get("component_group", ""): r.get("new_qty", 0)
                       for r in bom_rows}

        cad_gen = SofaCADGenerator(
            L          = length_mm,
            W          = width_mm,
            H          = height_mm,
            bom        = bom_for_cad,
            request_id = request_id,
            sofa_type  = sofa_type,
        )
        cad_out_dir = OUTPUTS_DIR / "cad"
        cad_out_dir.mkdir(parents=True, exist_ok=True)

        png_path = cad_gen.export_png(str(cad_out_dir))
        dxf_path = cad_gen.export_dxf(str(cad_out_dir))

        if Path(png_path).exists():
            shutil.copy2(png_path, request_folder / Path(png_path).name)
            cad_preview_url = f"/outputs/cad/{Path(png_path).name}"
        if Path(dxf_path).exists():
            shutil.copy2(dxf_path, request_folder / Path(dxf_path).name)
            cad_dxf_url = f"/outputs/cad/{Path(dxf_path).name}"

        # ── 3D mesh preview (GLB / OBJ / PNG) ───────────────────────────────
        cad_glb_url     = None
        cad_3d_prev_url = None
        _set_progress(progress_id, "model3d")
        try:
            scene_3d = build_sofa_mesh(
                scaled_bom=bom_for_cad,
                dimensions={"length_mm": length_mm, "width_mm": width_mm, "height_mm": height_mm},
                sofa_type=sofa_type,
            )
            model_paths = export_3d_model(scene_3d, str(cad_out_dir), request_id)
            preview_3d  = render_preview_image(scene_3d, str(cad_out_dir), request_id)

            glb_p = Path(model_paths["glb_path"])
            if glb_p.exists():
                shutil.copy2(glb_p, request_folder / glb_p.name)
                cad_glb_url = f"/outputs/cad/{glb_p.name}"

            prev_p = Path(preview_3d)
            if prev_p.exists():
                shutil.copy2(prev_p, request_folder / prev_p.name)
                cad_3d_prev_url = f"/outputs/cad/{prev_p.name}"
        except Exception as exc:
            print(f"[CAD-3D] 3D mesh generation failed for {request_id}: {exc}")

        step_path = cad_out_dir / f"{request_id}.step"
        _set_progress(progress_id, "step")
        try:
            written = build_sofa_step_model(
                sofa_type=sofa_type,
                output_path=step_path,
                dimensions={
                    "length_mm": length_mm,
                    "width_mm": width_mm,
                    "height_mm": height_mm,
                },
            )
            if written and Path(written).exists():
                shutil.copy2(written, request_folder / Path(written).name)
                cad_step_url = f"/outputs/cad/{Path(written).name}"
        except Exception as exc:
            print(f"[CAD] STEP generation failed for request {request_id}: {exc}")

    except Exception as exc:
        cad_error = str(exc)

    # Save input request JSON
    with open(request_folder / "input_request.json", "w") as f:
        json.dump({
            "request_id":    request_id,
            "customer_name": customer_name,
            "sofa_type":     sofa_type,
            "image_path":    str(image_path),
            "dimensions_mm": {"length": length_mm, "width": width_mm, "height": height_mm},
        }, f, indent=4)

    response = {
        "status":       "success",
        "request_id":   request_id,
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "customer_name": customer_name,
        "dimensions_mm": {"length": length_mm, "width": width_mm, "height": height_mm},
        "image_metadata":       image_result["metadata"],
        "sofa_analysis":        sofa_result,
        "sofa_type":            sofa_type,
        "type_mismatch":        type_mismatch,
        "estimated_dimensions": estimated_dimensions,
        "bom":               merged_bom,
        "quote":             summary,
        "annotated_image_url": annotated_url,
        "cad_preview_url":   cad_preview_url,
        "cad_dxf_url":       cad_dxf_url,
        "cad_step_url":      cad_step_url,
        "cad_glb_url":       cad_glb_url,
        "cad_3d_preview_url": cad_3d_prev_url,
        "pdf_url":           f"/api/quotes/{request_id}/pdf",
        **({"cad_error": cad_error} if cad_error else {}),
    }
    # Saved so the quote can be reopened from history and turned into a PDF
    (request_folder / "response.json").write_text(json.dumps(response, indent=2), encoding="utf-8")
    _set_progress(progress_id, "done")
    return JSONResponse(response)





