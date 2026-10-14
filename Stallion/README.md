# Stallion Sofa Costing Engine

**Overall Status**: ✅ All planned integration work complete — full pipeline operational

Stallion is an **image-validated sofa quotation pipeline** that takes a single sofa photograph plus physical dimensions and produces:

- A structured cost estimate (Bill of Materials scaled to user dimensions)
- A 2D technical drawing sheet (3-view projection, PNG + DXF)
- A 3D component-based preview (GLB/OBJ + PNG thumbnail)
- A STEP production CAD file (BREP-based, via build123d)
- Quote output files: summary JSON, BOM CSV, cost breakdown CSV
- An **image-assisted height estimate** with confidence score and suppression gating

The system is intended as a prototype-grade internal engineering tool, not a public SaaS product.

## High-Level Architecture

```text
User Input: sofa image + length/width/height (mm)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI  (src/api.py)  POST /api/quote                 │
│  Web UI   (frontend/index.html)  GET /                  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────┐    ┌──────────────────────────────────┐
│ Image Processor  │───→│ Sofa Validator                   │
│ (image_processor)│    │ (sofa_validator + YOLOv8 COCO /  │
│                  │    │  Stallion trained detector)       │
└──────────────────┘    └──────────────────────────────────┘
                                     │
                        ┌────────────┘
                        │
                        ▼
          ┌──────────────────────────────────┐
          │ Dimension Estimator              │
          │ (dimension_estimator_api)        │
          └──────────────────────────────────┘
                        │
                        ▼
          ┌──────────────────────────────────┐
          │ Cost Engine (cost_engine)        │
          │ (CSV-driven & Schema-driven)     │
          └──────────────────────────────────┘
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
┌────────────────────┐  ┌──────────────────────────┐
│ CAD Generator      │  │ Production CAD           │
│ 2D: PNG + DXF      │  │ BREP/STEP via build123d  │
│ 3D: GLB/OBJ/PNG    │  │ All 5 sofa types         │
└────────────────────┘  └──────────────────────────┘
```

## Core Features

### 1. Image Intake & Validation
The `src/image_processor.py` validates file type, resolution (minimum 200x200), max size (50 MB), and OpenCV readability. It generates an `image_metadata.json` for downstream processing.

### 2. Sofa Detection & Classification
The validation layer (`src/sofa_validator.py`) uses a YOLOv8 segmentation detector (`data/models/weights/sofa_detector.pt`, COCO fallback if missing) to confirm there is a sofa and find its parts, and a separate type classifier (`sofa_type_classifier.pt`, YOLOv8s trained on square-padded photos; keep `sofa_type_classifier.json` next to it) to decide `1_seater` / `2_seater` / `3_seater` / `4_seater_plus` / `l_shape` (86.7% on held-out room photos, 93.5% on held-out catalogue photos). When it is less than 60% sure it shows its two best guesses instead of one. The quote is priced with the type the user selects; the detected type only flags a likely wrong selection. See [docs/07_MODELS.md](docs/07_MODELS.md) for how to rebuild the models and their measured accuracy.

### 3. Dimension Estimation
The `src/dimension_estimator.py` estimates the overall sofa height from the bounding box and a user-provided anchor length. It includes four confidence gates to suppress unreliable estimates, returning `estimated_dimensions` to the API.

### 4. Cost Engine & BOM Scaling
Implemented in `src/cost_engine.py`, it supports two modes:
- **CSV-driven (`generate_quote`)**: Uses `master_template_spec.csv` with 10 legacy groups.
- **Schema-driven (`generate_quote_from_schema`)**: Uses `component_schema_extended` with 28 granular components and Fusion 360 mappings.
Both modes apply scaling rules to produce scaled BOMs and cost estimates.

### 5. CAD Generation
- **2D drawings (`src/cad_generator.py`)**: multi-view 2D drawings (PNG, DXF).
- **3D model with the inside (`src/sofa_build.py` → `src/sofa_interior.py`, exported by `src/cad_generator_3d.py`)**: the sofa built part by part following the industry reference model "Sofa Internal Structure.f3z" — timber frame and arm frames, 12 mm plywood, sinuous springs and clips, seat and back belts, foam and fabric. The quote's quantities are measured off the same parts (`bom_geometry.py`). Exported as GLB and OBJ, plus an exploded GLB with the layers lifted apart. `src/reference_cad.py` reads the Fusion archive directly to re-measure the reference.
- **Production CAD (`src/production_cad.py`)**: Generates BREP/STEP models for all 5 sofa types via `build123d`.

## How to Run the Project

### Prerequisites & Dependencies
- Python 3.11+
- Virtual environment with pinned packages (see `requirements.txt`).
- Note: `build123d` (v0.11.1) is required for STEP generation but must be installed manually or added to `requirements.txt`.

### Install Dependencies
```bash
pip install -r requirements.txt
pip install build123d==0.11.1
```

### Run the Backend API
```bash
cd src
python -m uvicorn api:app --reload --port 8000
```
Then open the frontend in your browser at `http://localhost:8000/`.

The web app (`frontend/index.html` + ES modules in `frontend/js/`) offers:
- **Quote form** with per-type size ranges (from `master_dimensions.csv`, via `GET /api/config`), inline errors and photo guidance.
- **Type detection on upload** (`POST /api/detect-type`): as soon as a photo is chosen the type classifier runs; a confident result (≥ 60%) pre-selects the type and its size ranges, which the customer can still change. A live **3D preview** of the chosen type (`GET /api/model-preview`) follows the dimensions as they are typed.
- **Live progress** from the server (`GET /api/progress/{id}`) while the pipeline runs.
- **Results** with the annotated photo, BOM, cost structure, CAD downloads and a rotatable **3D model** (`<model-viewer>`, bundled in `frontend/vendor/` so it works offline). Turn **Fabric** and **Foam** off to see inside the sofa, or switch to **Exploded** to see each layer lifted apart (`GET /api/model-preview?...&exploded=true` gives the same model).
- **Quote PDF** (`GET /api/quotes/{id}/pdf`), branded with SVCE and Stallion.
- **Cost estimator**: material quantities are measured off the sofa built part by part like the industry reference model (`src/sofa_build.py`, `src/bom_geometry.py`: timber volume of every member, plywood area, foam volume x density, fabric from upholstered area and roll width), then priced with the rate sheet `data/pricing/pricing.json` (researched Bengaluru market rates with wastage %, fabric/foam grades, labour and finishing per sofa type, overhead and profit). Each quote shows the factory price (excl. GST) and a retail-equivalent estimate (dealer markup + 18% GST). Sources and assumptions: [docs/08_COSTING.md](docs/08_COSTING.md).
- **Rate editor** for staff (Staff → Rates, `GET/PUT /api/pricing`): every save is validated and the previous sheet is kept as `pricing.previous.json`.
- **Price vs size** (`GET /api/size-options`): the price at ±100 mm on each dimension, at today's rates.
- **Quote history** (`GET /api/quotes`) for staff. Set `STALLION_STAFF_KEY` on a shared server; staff enter it once per browser session. Without it, history only works from the server machine itself. Behind a reverse proxy every request looks local, so **always set the key there**.

Optional environment variables:

| Variable | Purpose |
|---|---|
| `STALLION_STAFF_KEY` | Key required to view quote history |
| `STALLION_ALLOWED_ORIGINS` | Comma-separated origins allowed to call the API from another site |
| `STALLION_PDF_NOTE` | Note printed under the PDF total (default: indicative-quotation wording) |

### Run via CLI
```bash
cd src
python run_quote.py --input ../data/sample_inputs/sample_request.json
```

## Output Artifacts

Outputs are saved in the `outputs/` directory and include:
- **quotations/**: JSON summaries and cost CSVs.
- **bom_outputs/**: Scaled BOM CSVs.
- **cad/**: PNG/DXF 2D drawings and GLB/OBJ 3D models.
- **production_cad/**: STEP files for the evaluated sofas.

## Test Suite Health
The project is currently passing all tests:
- `tests/` directory contains 78 passing tests covering schemas, CAD generation, the 3D interior model (part counts and size match the quote, and the 3-seater matches the reference model part by part), cost scaling per sofa type, the type classifier's padding, and the quote API.
- Root-level validation scripts (`test_detector_fix_validation.py`, `test_dimension_estimator.py`, etc.) all pass.

## Known Issues & Limitations
- **Rates are researched, not quoted**: `data/pricing/pricing.json` holds researched market rates and an assumed construction spec, not the factory's supplier quotes. Replace them in the staff rate editor (see [docs/08_COSTING.md](docs/08_COSTING.md)).
- **ML Models**: Training data lives outside git (`merged_sofa_dataset.zip` for the detector, `data/datasets/raw/` for the type classifier). The type classifier also uses hand-reviewed web room photos (gitignored); 4-seater is its weakest type on room photos. Details and numbers in [docs/07_MODELS.md](docs/07_MODELS.md).
- **Frontend Dimension UX**: The API returns estimated dimensions, but the frontend (`frontend/index.html`) does not yet render the UI for users to confirm or override these heights.


## Next Steps
1. Add dimension estimation UX to the frontend.
2. Validate the dimension estimator with real sofa photos.

4. Ingest real pricing and BOM data from the manufacturing team.
5. Collect more 3-seater / 4-seater photos and some real room photos for testing.
