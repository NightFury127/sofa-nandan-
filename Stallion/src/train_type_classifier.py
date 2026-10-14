"""
train_type_classifier.py — Train a YOLOv8 classifier that predicts sofa type
(1_seater / 2_seater / 3_seater / l_shape) from a whole photo.

Input:   data/datasets/processed/sofa_types/   (run prepare_type_dataset.py first)
Output:  data/models/weights/sofa_type_classifier_candidate.pt — not the live
         sofa_type_classifier.pt. Compare with
         `python eval_sofa_types.py --classifier ../data/models/weights/sofa_type_classifier_candidate.pt`
         and copy it over the live file only if it scores better.
Runs:    outputs/training_runs/type_classifier_<timestamp>/

Under-represented types are oversampled in the training split (copies of the
same photos) so the model doesn't learn to always answer "2_seater".
Validation and test splits are never oversampled.

Run:
    python train_type_classifier.py                          # yolov8s-cls at 320px
    python train_type_classifier.py --model yolov8n-cls.pt --img 224   # the original, smaller setup
"""

import argparse
import math
import shutil
from datetime import datetime
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
DATASET_DIR  = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types"
TRAIN_DIR    = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types_train"
WEIGHTS_OUT  = PROJECT_ROOT / "data" / "models" / "weights" / "sofa_type_classifier_candidate.pt"
RUNS_DIR     = PROJECT_ROOT / "outputs" / "training_runs"

# Each type is oversampled up to this fraction of the largest type's count
MIN_CLASS_FRACTION = 0.5


def build_training_copy(extra_train=None, dataset_dir: Path = DATASET_DIR,
                        balance: float = MIN_CLASS_FRACTION) -> Path:
    """
    Copy train/ (plus any extra_train/<type>/ photos, e.g. room composites from
    augment_type_dataset.py), oversample small types, and copy val/ unchanged.
    """
    if not (dataset_dir / "train").exists():
        raise SystemExit(f"[ERROR] {dataset_dir} not found — run prepare_type_dataset.py first.")

    if TRAIN_DIR.exists():
        shutil.rmtree(TRAIN_DIR)
    shutil.copytree(dataset_dir / "val", TRAIN_DIR / "val")

    class_dirs = sorted(p for p in (dataset_dir / "train").iterdir() if p.is_dir())
    for d in class_dirs:
        shutil.copytree(d, TRAIN_DIR / "train" / d.name)
        if extra_train and (Path(extra_train) / d.name).exists():
            for f in (Path(extra_train) / d.name).iterdir():
                shutil.copy2(f, TRAIN_DIR / "train" / d.name / f.name)

    counts = {d.name: len(list((TRAIN_DIR / "train" / d.name).iterdir())) for d in class_dirs}
    target = math.ceil(max(counts.values()) * balance)

    for d in class_dirs:
        dst = TRAIN_DIR / "train" / d.name
        files = sorted(dst.iterdir())
        copies = 0
        while len(files) + copies < target:
            src = files[copies % len(files)]
            shutil.copy2(src, dst / f"{src.stem}_os{copies}{src.suffix}")
            copies += 1
        print(f"  {d.name:<14} {counts[d.name]:>4} photos" + (f"  (+{copies} oversampled)" if copies else ""))

    return TRAIN_DIR


def train(base_model: str, epochs: int, img_size: int, batch: int, device: str, extra_train=None,
          dataset_dir: Path = DATASET_DIR, balance: float = MIN_CLASS_FRACTION,
          patience: int = 10, workers: int = 8):
    from ultralytics import YOLO

    data_dir = build_training_copy(extra_train, dataset_dir, balance)
    run_name = f"type_classifier_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    model = YOLO(base_model)
    model.train(
        data     = str(data_dir),
        epochs   = epochs,
        imgsz    = img_size,
        batch    = batch,
        device   = device,
        project  = str(RUNS_DIR),
        name     = run_name,
        patience = patience,
        workers  = workers,
        seed     = 42,
        plots    = True,
        verbose  = False,
    )

    best = RUNS_DIR / run_name / "weights" / "best.pt"
    if not best.exists():
        raise SystemExit(f"[ERROR] Training finished but {best} was not written.")
    WEIGHTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, WEIGHTS_OUT)
    print(f"\nCandidate weights copied to {WEIGHTS_OUT}")
    print(f"Next: python eval_sofa_types.py --classifier {WEIGHTS_OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model",  default="yolov8s-cls.pt", help="Base model (yolov8n/s/m-cls.pt)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--img",    type=int, default=320)
    ap.add_argument("--batch",  type=int, default=32)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--extra-train", help="Extra <dir>/<type>/ training photos (e.g. room composites)")
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR,
                    help="Split to train on (default processed/sofa_types; v2 with room photos: processed/sofa_types_v2)")
    ap.add_argument("--balance", type=float, default=MIN_CLASS_FRACTION,
                    help="Oversample each type up to this fraction of the largest (default 0.5; 1.0 = equal)")
    ap.add_argument("--patience", type=int, default=10, help="Stop after this many epochs without improvement")
    ap.add_argument("--workers", type=int, default=8, help="Data-loading processes (fewer uses less RAM)")
    args = ap.parse_args()
    train(args.model, args.epochs, args.img, args.batch, args.device, args.extra_train, args.dataset, args.balance,
          args.patience, args.workers)
