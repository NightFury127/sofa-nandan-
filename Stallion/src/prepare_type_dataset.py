"""
prepare_type_dataset.py — Build a train/val/test split for the sofa-type classifier.

Source:  data/datasets/raw/<folder>/*.jpg   (one folder per sofa type)
Output:  data/datasets/processed/sofa_types/{train,val,test}/<type>/

- Exact duplicate photos (same bytes) are kept once, so a copy can't sit in
  both train and test.
- Photos that appear in two different type folders are dropped and listed in
  label_conflicts.txt for review.
- Types with too few unique photos to split are skipped (reported).
- The split is stratified and seeded, so it is reproducible.

Run:
    python prepare_type_dataset.py
"""

import hashlib
import random
import shutil
from collections import defaultdict
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
RAW_DIR      = PROJECT_ROOT / "data" / "datasets" / "raw"
OUT_DIR      = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types"

# Raw folder name -> label used by the pipeline (matches sofa_validator types)
FOLDER_TO_TYPE = {
    "1-seater": "1_seater",
    "2-seater": "2_seater",
    "3-seater": "3_seater",
    "4-seater": "4_seater_plus",
    "L-shape":  "l_shape",
}
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp"}
SPLITS       = (("train", 0.70), ("val", 0.15), ("test", 0.15))
MIN_PER_TYPE = 20
SEED         = 42


def _collect():
    """Return {type: [paths]} with duplicates collapsed and conflicts removed."""
    by_hash = defaultdict(list)
    for folder, sofa_type in FOLDER_TO_TYPE.items():
        for p in sorted((RAW_DIR / folder).glob("*")):
            if p.suffix.lower() in IMAGE_EXTS:
                by_hash[hashlib.md5(p.read_bytes()).hexdigest()].append((sofa_type, p))

    images, conflicts = defaultdict(list), []
    for entries in by_hash.values():
        types = {t for t, _ in entries}
        if len(types) > 1:
            conflicts.append(entries)
            continue
        sofa_type, path = entries[0]
        images[sofa_type].append(path)
    return images, conflicts, len(by_hash)


def main():
    images, conflicts, n_unique = _collect()

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    rng = random.Random(SEED)
    summary = {}
    for sofa_type, paths in sorted(images.items()):
        if len(paths) < MIN_PER_TYPE:
            print(f"[skip] {sofa_type}: only {len(paths)} unique photos (need {MIN_PER_TYPE})")
            continue
        rng.shuffle(paths)
        n_train = round(len(paths) * SPLITS[0][1])
        n_val   = round(len(paths) * SPLITS[1][1])
        parts   = {"train": paths[:n_train],
                   "val":   paths[n_train:n_train + n_val],
                   "test":  paths[n_train + n_val:]}
        for split, split_paths in parts.items():
            dst = OUT_DIR / split / sofa_type
            dst.mkdir(parents=True, exist_ok=True)
            for p in split_paths:
                shutil.copy2(p, dst / p.name)
        summary[sofa_type] = {k: len(v) for k, v in parts.items()}

    with open(OUT_DIR / "label_conflicts.txt", "w") as f:
        f.write("Identical photos found in more than one type folder (excluded):\n")
        for entries in conflicts:
            f.write("  " + "  ==  ".join(f"{p.parent.name}/{p.name}" for _, p in entries) + "\n")

    print(f"{n_unique} unique photos, {len(conflicts)} label conflicts excluded")
    for sofa_type, counts in summary.items():
        print(f"  {sofa_type:<14} train {counts['train']:>4}  val {counts['val']:>3}  test {counts['test']:>3}")
    print(f"Written to {OUT_DIR}")


if __name__ == "__main__":
    main()
