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
The validation layer (`src/sofa_validator.py`) uses a YOLO object detection pipeline. It uses `StallionSofaDetector` (trained on `models/sofa_detector.pt`) or a COCO fallback. It classifies the sofa as `1_seater`, `2_seater`, `3_seater`, `4_seater_plus`, or `l_shape` based on bounding box aspect ratio and multiple overlapping detections.

### 3. Dimension Estimation
The `src/dimension_estimator.py` estimates the overall sofa height from the bounding box and a user-provided anchor length. It includes four confidence gates to suppress unreliable estimates, returning `estimated_dimensions` to the API.

### 4. Cost Engine & BOM Scaling
Implemented in `src/cost_engine.py`, it supports two modes:
- **CSV-driven (`generate_quote`)**: Uses `master_template_spec.csv` with 10 legacy groups.
- **Schema-driven (`generate_quote_from_schema`)**: Uses `component_schema_extended` with 28 granular components and Fusion 360 mappings.
Both modes apply scaling rules to produce scaled BOMs and cost estimates.

### 5. CAD Generation
- **2D/3D Approximations (`src/cad_generator.py` & `src/cad_generator_3d.py`)**: Generates multi-view 2D drawings (PNG, DXF) and 3D preview meshes (GLB, OBJ) representing a component-based approximation of the sofa.
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
- `tests/` directory contains 22 passing tests covering schemas, CAD generation, and phase validations.
- Root-level validation scripts (`test_detector_fix_validation.py`, `test_dimension_estimator.py`, etc.) all pass.

## Known Issues & Limitations
- **Data Placeholders**: Pricing (`cost_sheet.csv`) and BOM quantities are currently placeholders. Real production data is pending.
- **ML Dataset**: The YOLOv8 model was trained primarily on 3-seater images. Multi-class accuracy is unverified without retraining on a broader dataset. 4-seater images are severely under-represented.
- **Frontend Dimension UX**: The API returns estimated dimensions, but the frontend (`frontend/index.html`) does not yet render the UI for users to confirm or override these heights.


## Next Steps
1. Add dimension estimation UX to the frontend.
2. Validate the dimension estimator with real sofa photos.

4. Ingest real pricing and BOM data from the manufacturing team.
5. Retrain `sofa_detector.pt` on a merged dataset with a balanced class distribution.
