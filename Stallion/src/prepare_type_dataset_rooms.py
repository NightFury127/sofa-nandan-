"""
prepare_type_dataset_rooms.py — Build the v2 sofa-type dataset: the catalogue
split from prepare_type_dataset.py plus the hand-reviewed web room photos
(collect_web_photos.py), with a separate room-photo test split.

Input:   data/datasets/processed/sofa_types/{train,val,test}/<type>/   (catalogue split, unchanged)
         data/datasets/collected/web/reviewed/<type>/                  (reviewed room photos)
         data/datasets/raw/4-seater/                                   (catalogue 4-seaters, train only)
Output:  data/datasets/processed/sofa_types_v2/{train,val,test,test_rooms}/<type>/

- The catalogue train/val/test split is copied as-is, so catalogue test
  scores stay comparable with models trained on v1.
- Room photos are split per type, seeded: 60% train, 10% val, 30% test_rooms.
- 4_seater_plus becomes a class: room photos plus the 3 catalogue 4-seaters
  (train only, too few to test on).

Run:
    python prepare_type_dataset.py          # first, if processed/sofa_types/ is missing
    python prepare_type_dataset_rooms.py
    python train_type_classifier.py --dataset ../data/datasets/processed/sofa_types_v2
    python eval_sofa_types.py --dir ../data/datasets/processed/sofa_types_v2/test_rooms
"""

import random
import shutil
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
DATASETS     = PROJECT_ROOT / "data" / "datasets"
CATALOGUE    = DATASETS / "processed" / "sofa_types"
ROOMS        = DATASETS / "collected" / "web" / "reviewed"
RAW_4SEATER  = DATASETS / "raw" / "4-seater"
OUT_DIR      = DATASETS / "processed" / "sofa_types_v2"

ROOM_SPLITS = (("train", 0.60), ("val", 0.10), ("test_rooms", 0.30))
IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".webp"}
SEED        = 42


def _images(d: Path):
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS) if d.exists() else []


def main():
    if not (CATALOGUE / "train").exists():
        raise SystemExit(f"[ERROR] {CATALOGUE} not found — run prepare_type_dataset.py first.")
    if not ROOMS.exists():
        raise SystemExit(f"[ERROR] {ROOMS} not found — run collect_web_photos.py --apply-review first.")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for split in ("train", "val", "test"):
        shutil.copytree(CATALOGUE / split, OUT_DIR / split)

    counts = {}
    for type_dir in sorted(p for p in ROOMS.iterdir() if p.is_dir()):
        photos = _images(type_dir)
        # Seeded per type, so adding photos to one type doesn't reshuffle the others
        random.Random(f"{SEED}:{type_dir.name}").shuffle(photos)
        n_train = round(len(photos) * ROOM_SPLITS[0][1])
        n_val   = round(len(photos) * ROOM_SPLITS[1][1])
        parts = {"train":      photos[:n_train],
                 "val":        photos[n_train:n_train + n_val],
                 "test_rooms": photos[n_train + n_val:]}
        for split, split_photos in parts.items():
            dst = OUT_DIR / split / type_dir.name
            dst.mkdir(parents=True, exist_ok=True)
            for p in split_photos:
                shutil.copy2(p, dst / f"web_{p.name}")
        counts[type_dir.name] = {k: len(v) for k, v in parts.items()}

    dst = OUT_DIR / "train" / "4_seater_plus"
    dst.mkdir(parents=True, exist_ok=True)
    for p in _images(RAW_4SEATER):
        shutil.copy2(p, dst / f"raw_{p.name}")

    print(f"Written {OUT_DIR}")
    print(f"  {'type':<14} {'train':>6} {'val':>5} {'test':>5} {'test_rooms':>11}   (room photos in train/val)")
    for split_type in sorted({d.name for d in (OUT_DIR / 'train').iterdir()}):
        n = {s: len(_images(OUT_DIR / s / split_type)) for s in ("train", "val", "test", "test_rooms")}
        c = counts.get(split_type, {})
        print(f"  {split_type:<14} {n['train']:>6} {n['val']:>5} {n['test']:>5} {n['test_rooms']:>11}"
              f"   ({c.get('train', 0)}/{c.get('val', 0)})")


if __name__ == "__main__":
    main()
