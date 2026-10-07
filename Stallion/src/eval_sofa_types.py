"""
eval_sofa_types.py — Measure how often the pipeline gets the sofa TYPE right.

Scores, on the same held-out photos:
  detector    the YOLO detector + _classify_type rules (sofa_validator.py)
  classifier  the sofa-type classifier (sofa_type_classifier.pt), if trained

Data: data/datasets/processed/sofa_types/test/<type>/  (prepare_type_dataset.py)
      --split val|train to score another split instead.

Reports a confusion matrix, per-type recall, overall accuracy and balanced
accuracy (mean per-type recall — the fairer number, since 2-seaters dominate).
Writes outputs/eval/sofa_types_<timestamp>.json.

Run:
    python eval_sofa_types.py
    python eval_sofa_types.py --split val
    python eval_sofa_types.py --classifier ../data/models/weights/sofa_type_classifier_candidate.pt
    python eval_sofa_types.py --dir ../data/datasets/collected/reviewed   # any <dir>/<type>/ folder

Also prints the classifier's accuracy at different confidence cut-offs, used
to pick TYPE_CONFIDENCE_THRESHOLD in sofa_validator.py.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
DATASET_DIR  = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types"
EVAL_DIR     = PROJECT_ROOT / "outputs" / "eval"

sys.path.insert(0, str(SRC_DIR))

TYPES = ["1_seater", "2_seater", "3_seater", "4_seater_plus", "l_shape"]


def _score(name, rows):
    """rows: list of (truth, pred). Print a confusion matrix and return metrics."""
    labels = TYPES + sorted({p for _, p in rows} - set(TYPES))
    truths = [t for t in TYPES if any(r[0] == t for r in rows)]
    matrix = defaultdict(Counter)
    for t, p in rows:
        matrix[t][p] += 1

    print(f"\n── {name} " + "─" * (60 - len(name)))
    print("truth \\ pred".ljust(14) + "".join(l[:9].rjust(10) for l in labels) + "   recall")
    recalls = {}
    for t in truths:
        n = sum(matrix[t].values())
        recalls[t] = matrix[t][t] / n
        print(t.ljust(14) + "".join(str(matrix[t][l]).rjust(10) for l in labels)
              + f"   {recalls[t]:6.1%}  (n={n})")
    correct = sum(matrix[t][t] for t in truths)
    accuracy = correct / len(rows)
    balanced = sum(recalls.values()) / len(recalls)
    print(f"accuracy {accuracy:.1%} ({correct}/{len(rows)})   balanced accuracy {balanced:.1%}")
    return {"accuracy": accuracy, "balanced_accuracy": balanced, "recall": recalls,
            "confusion": {t: dict(matrix[t]) for t in truths}}


def _confidence_table(scored):
    """scored: list of (truth, pred, conf). Accuracy and coverage at each cut-off."""
    print("\n   cut-off   kept        accuracy of kept   accuracy of the rest")
    table = {}
    for cut in (0.5, 0.6, 0.7, 0.8, 0.9):
        kept = [(t, p) for t, p, c in scored if c >= cut]
        rest = [(t, p) for t, p, c in scored if c < cut]
        acc  = sum(t == p for t, p in kept) / len(kept) if kept else 0.0
        racc = sum(t == p for t, p in rest) / len(rest) if rest else None
        table[cut] = {"kept": len(kept), "accuracy_kept": acc, "accuracy_rest": racc}
        rest_txt = f"{racc:6.1%} (n={len(rest)})" if rest else "   —"
        print(f"   >= {cut:.1f}   {len(kept):>4}/{len(scored):<4}     {acc:6.1%}             {rest_txt}")
    return table


def main(split: str, classifier_path=None, photo_dir=None):
    split_dir = Path(photo_dir) if photo_dir else DATASET_DIR / split
    if not split_dir.exists():
        raise SystemExit(f"[ERROR] {split_dir} not found — run prepare_type_dataset.py first.")
    photos = [(d.name, p) for d in sorted(split_dir.iterdir()) if d.is_dir()
              for p in sorted(d.iterdir()) if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    source = str(split_dir) if photo_dir else f"the '{split}' split"
    print(f"Scoring {len(photos)} photos from {source}")

    report = {"split": source, "n_photos": len(photos), "results": {}}

    from sofa_validator import get_detector, _classify_type
    detector = get_detector()
    rows = []
    for truth, p in photos:
        dets = detector.detect(str(p))
        rows.append((truth, _classify_type(dets) if dets else "NO_SOFA"))
    report["results"]["detector"] = _score(f"detector ({type(detector).__name__})", rows)

    from sofa_type_classifier import SofaTypeClassifier, get_type_classifier
    if classifier_path:
        classifier, label = SofaTypeClassifier(Path(classifier_path)), Path(classifier_path).name
    else:
        classifier, label = get_type_classifier(), "sofa_type_classifier.pt"
    if classifier is None:
        print("\n(classifier weights not found — run train_type_classifier.py to compare)")
    else:
        scored = [(truth, *classifier.predict(str(p))) for truth, p in photos]
        report["results"]["classifier"] = _score(f"classifier ({label})", [(t, p) for t, p, _ in scored])
        report["results"]["classifier"]["by_confidence"] = _confidence_table(scored)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    tag = Path(photo_dir).name if photo_dir else split
    out = EVAL_DIR / f"sofa_types_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--classifier", help="Classifier weights to score instead of the live one")
    ap.add_argument("--dir", help="Score photos in <dir>/<type>/ instead of a prepared split")
    args = ap.parse_args()
    main(args.split, args.classifier, args.dir)
