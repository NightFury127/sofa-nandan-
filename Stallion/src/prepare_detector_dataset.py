"""
prepare_detector_dataset.py — Build the v2 detector dataset with the three
Stallion classes merged into one.

Input:   data/datasets/detector/          (merged_dataset, 11 classes; see docs/07_MODELS.md)
Output:  data/datasets/detector_v2/       (9 classes)

Why: "stallion-sofa", "stallion-sofa1" and "stallion-sofa2" are the same
product and the pipeline treats all three as a 3-seater. Split three ways,
each class has only 51-67 labels and scores 0.31-0.67 AP50; merged, the model
learns one class from all 176.

v2 classes: 0-5 sofa parts (unchanged), 6 one-seater, 7 stallion-sofa, 8 two-seater.
sofa_validator.py maps detections by class name, so it works with either.

Run:
    python prepare_detector_dataset.py
    python train_model.py --data ../data/datasets/detector_v2/data.yaml --epochs 50
"""

import shutil
from collections import Counter
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
IN_DIR       = PROJECT_ROOT / "data" / "datasets" / "detector"
OUT_DIR      = PROJECT_ROOT / "data" / "datasets" / "detector_v2"

IN_NAMES  = ["back_cushion", "base", "left_arm", "legs", "right_arm", "seat_cushion",
             "one-seater", "stallion-sofa1", "stallion-sofa2", "stallion-sofa", "two-seater"]
OUT_NAMES = ["back_cushion", "base", "left_arm", "legs", "right_arm", "seat_cushion",
             "one-seater", "stallion-sofa", "two-seater"]
REMAP = {IN_NAMES.index(n): OUT_NAMES.index(n.rstrip("12")) for n in IN_NAMES}


def main():
    if not (IN_DIR / "data.yaml").exists():
        raise SystemExit(f"[ERROR] {IN_DIR / 'data.yaml'} not found — unzip merged_sofa_dataset.zip first.")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    counts = Counter()
    for split in ("train", "valid"):
        shutil.copytree(IN_DIR / split / "images", OUT_DIR / split / "images")
        out_labels = OUT_DIR / split / "labels"
        out_labels.mkdir(parents=True)
        for lab in (IN_DIR / split / "labels").glob("*.txt"):
            lines = []
            for line in lab.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                new_id = REMAP[int(parts[0])]
                counts[OUT_NAMES[new_id]] += 1
                lines.append(" ".join([str(new_id)] + parts[1:]))
            (out_labels / lab.name).write_text("\n".join(lines) + ("\n" if lines else ""))

    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(OUT_NAMES))
    (OUT_DIR / "data.yaml").write_text(
        f"path: {OUT_DIR.as_posix()}\ntrain: train/images\nval: valid/images\n\nnc: {len(OUT_NAMES)}\nnames:\n{names}\n"
    )
    print(f"Written {OUT_DIR}")
    for n in OUT_NAMES:
        print(f"  {n:<14} {counts[n]:>5} labels")


if __name__ == "__main__":
    main()
