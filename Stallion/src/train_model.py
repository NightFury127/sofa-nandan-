"""
train_model.py — Train the YOLOv8 segmentation sofa detector.

Dataset:  a YOLO segmentation dataset (data.yaml + train/ + valid/), passed with
          --data, default data/datasets/detector/data.yaml.
          NOTE: the dataset behind the current sofa_detector.pt ("merged_dataset",
          11 classes: 6 sofa parts + one-seater, stallion-sofa1/2, stallion-sofa,
          two-seater) is not in this repo. Put a copy at the default path or
          pass --data. The pipeline relies on the stallion-sofa* classes to
          recognise the Stallion product, so keep them in any retrain.
Output:   data/models/weights/sofa_detector_candidate.pt — never the live
          sofa_detector.pt. Score the candidate with eval_model.py and
          eval_sofa_types.py first, then copy it over sofa_detector.pt.
Runs:     outputs/training_runs/stallion_<timestamp>/

Run:
    python train_model.py --data path/to/data.yaml
    python train_model.py --data path/to/data.yaml --epochs 100 --batch 8 --img 640
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
DATA_YAML    = PROJECT_ROOT / "data" / "datasets" / "detector" / "data.yaml"
MODELS_DIR   = PROJECT_ROOT / "data" / "models" / "weights"
CANDIDATE    = MODELS_DIR / "sofa_detector_candidate.pt"
RUNS_DIR     = PROJECT_ROOT / "outputs" / "training_runs"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def patch_data_yaml(data_yaml: Path) -> Path:
    """
    YOLOv8 needs absolute paths in data.yaml when called from a different CWD.
    We write a patched copy with absolute train/val paths so it works from anywhere.
    """
    import yaml  # pyyaml — installed with ultralytics

    with open(data_yaml) as f:
        cfg = yaml.safe_load(f)

    dataset_root = data_yaml.parent.resolve()
    cfg["path"] = str(dataset_root)
    cfg["train"] = "train/images"
    cfg["val"]   = "valid/images"

    patched_path = dataset_root / "_data_abs.yaml"
    with open(patched_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    return patched_path


def train(data_yaml: Path, epochs: int, batch: int, img_size: int, device: str, resume: bool):
    from ultralytics import YOLO

    print(f"\n{'='*60}")
    print(f"  Stallion Sofa — YOLOv8 Segmentation Training")
    print(f"  Epochs: {epochs}  |  Batch: {batch}  |  Img: {img_size}")
    print(f"  Dataset: {data_yaml}")
    print(f"{'='*60}\n")

    if not data_yaml.exists():
        print(f"[ERROR] data.yaml not found at: {data_yaml}")
        print("  The current detector's training set (merged_dataset) is not in this repo;")
        print("  pass --data with a YOLO segmentation dataset (see the docstring).")
        sys.exit(1)

    # Patch yaml to absolute paths
    abs_yaml = patch_data_yaml(data_yaml)

    # Run name with timestamp
    run_name = f"stallion_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Load base model (segmentation variant)
    model = YOLO("yolov8n-seg.pt")

    # Train
    results = model.train(
        data     = str(abs_yaml),
        epochs   = epochs,
        batch    = batch,
        imgsz    = img_size,
        device   = device,
        name     = run_name,
        project  = str(RUNS_DIR),
        patience = 20,           # early stopping
        save     = True,
        plots    = True,
        resume   = resume,
        # Augmentation — conservative for small dataset
        degrees  = 10.0,
        flipud   = 0.1,
        fliplr   = 0.5,
        mosaic   = 0.8,
        mixup    = 0.0,
        hsv_h    = 0.015,
        hsv_s    = 0.5,
        hsv_v    = 0.3,
    )

    # ── Save best weights as a candidate (never overwrite the live model) ────
    best_weights = RUNS_DIR / run_name / "weights" / "best.pt"
    if best_weights.exists():
        shutil.copy2(best_weights, CANDIDATE)
        print(f"\n[✓] Candidate weights saved → {CANDIDATE}")
        print("    Not live yet: evaluate it, then copy it over sofa_detector.pt.")
    else:
        print(f"\n[!] best.pt not found at {best_weights}")

    # ── Save training summary JSON ────────────────────────────────────────────
    try:
        summary = {
            "run_name":     run_name,
            "epochs":       epochs,
            "batch":        batch,
            "img_size":     img_size,
            "best_weights": str(CANDIDATE),
            "run_dir":      str(RUNS_DIR / run_name),
            "metrics": {
                "box_map50":  float(results.results_dict.get("metrics/mAP50(B)",  0)),
                "seg_map50":  float(results.results_dict.get("metrics/mAP50(M)",  0)),
                "precision":  float(results.results_dict.get("metrics/precision(B)", 0)),
                "recall":     float(results.results_dict.get("metrics/recall(B)",    0)),
            },
        }
        summary_path = MODELS_DIR / "training_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=4)
        print(f"[✓] Training summary → {summary_path}")
        print(f"\n  mAP@50 (box): {summary['metrics']['box_map50']:.3f}")
        print(f"  mAP@50 (seg): {summary['metrics']['seg_map50']:.3f}")
        print(f"  Precision:    {summary['metrics']['precision']:.3f}")
        print(f"  Recall:       {summary['metrics']['recall']:.3f}")
    except Exception as e:
        print(f"[!] Could not save summary: {e}")

    print(f"\n[✓] Training complete. Run dir: {RUNS_DIR / run_name}\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Stallion sofa segmentation model")
    parser.add_argument("--data",   type=Path,  default=DATA_YAML, help="Path to the dataset's data.yaml")
    parser.add_argument("--epochs", type=int,   default=80,    help="Training epochs (default 80)")
    parser.add_argument("--batch",  type=int,   default=8,     help="Batch size (default 8)")
    parser.add_argument("--img",    type=int,   default=640,   help="Image size (default 640)")
    parser.add_argument("--device", type=str,   default="cpu", help="Device: cpu / 0 / cuda")
    parser.add_argument("--resume", action="store_true",       help="Resume from last checkpoint")
    args = parser.parse_args()

    train(
        data_yaml = args.data,
        epochs   = args.epochs,
        batch    = args.batch,
        img_size = args.img,
        device   = args.device,
        resume   = args.resume,
    )
