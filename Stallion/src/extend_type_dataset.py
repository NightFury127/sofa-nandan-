"""
extend_type_dataset.py — Add newly reviewed room photos to the type-classifier
dataset without disturbing the existing split.

prepare_type_dataset_rooms.py re-shuffles every reviewed room photo, so
re-running it after a new collection round would move photos between train
and test and make old and new models incomparable. This script keeps every
photo already in processed/sofa_types_v2/ where it is, and splits only the
new ones (seeded, per type): 70% train, 10% val, 20% into a separate
test_rooms_new/ split — mostly the hard cases each round was collected for.

It also writes the square-padded copy (no centre crop; see docs/07_MODELS.md).

Output:  processed/sofa_types_v3/{train,val,test,test_rooms,test_rooms_new}/<type>/
         processed/sofa_types_v3_sq/...   (same, padded to square)

Run:
    python extend_type_dataset.py
"""

import random
import shutil
from pathlib import Path

from PIL import Image

from sofa_type_classifier import pad_square

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "datasets" / "processed"
REVIEWED = Path(__file__).resolve().parent.parent / "data" / "datasets" / "collected" / "web" / "reviewed"
BASE, OUT = PROCESSED / "sofa_types_v2", PROCESSED / "sofa_types_v3"
SPLITS = (("train", 0.70), ("val", 0.10), ("test_rooms_new", 0.20))
SEED = 20261014


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(BASE, OUT, ignore=shutil.ignore_patterns("user_reports"))
    already = {p.name for p in BASE.rglob("web_*")}

    for type_dir in sorted(d for d in REVIEWED.iterdir() if d.is_dir()):
        new = sorted(p for p in type_dir.iterdir() if f"web_{p.name}" not in already)
        random.Random(f"{SEED}:{type_dir.name}").shuffle(new)
        start = 0
        counts = {}
        for i, (split, share) in enumerate(SPLITS):
            n = len(new) - start if i == len(SPLITS) - 1 else round(len(new) * share)
            for p in new[start:start + n]:
                dst = OUT / split / type_dir.name / f"web_{p.name}"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
            counts[split] = n
            start += n
        print(f"  {type_dir.name:<14} {len(new):>3} new  {counts}")

    sq = PROCESSED / "sofa_types_v3_sq"
    if sq.exists():
        shutil.rmtree(sq)
    for f in OUT.rglob("*"):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            out = sq / f.relative_to(OUT).with_suffix(".jpg")
            out.parent.mkdir(parents=True, exist_ok=True)
            img = pad_square(Image.open(f).convert("RGB"))
            img.thumbnail((640, 640))
            img.save(out, quality=92)
    for split in ("train", "val", "test", "test_rooms", "test_rooms_new"):
        d = OUT / split
        if d.exists():
            print(f"  {split:<15}", {t.name: len(list(t.iterdir())) for t in sorted(d.iterdir())})


if __name__ == "__main__":
    main()
