"""
augment_type_dataset.py — Make room-like versions of the white-background
training photos, to narrow the catalogue-vs-room gap.

Why: on 15 real room photos the classifier trained on catalogue shots scored
40% (vs 93.5% on catalogue test photos). Customers send room photos.

For each TRAIN photo with a white backdrop, the sofa is cut out (white pixels
connected to the image border are background), scaled to 40-85% of the frame
width and placed on a synthetic room: a wall with a random colour gradient,
a floor band (plain, or plank-striped like wood) and sensor noise.
Photos without a clear white backdrop are skipped.

Input:   data/datasets/processed/sofa_types/train/<type>/
Output:  data/datasets/processed/sofa_types_composited/<type>/
         Only training photos are used, so val/test stay untouched.

Run:
    python augment_type_dataset.py
    python train_type_classifier.py --extra-train ../data/datasets/processed/sofa_types_composited
"""

import random
import shutil
from pathlib import Path

import cv2
import numpy as np

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
IN_DIR       = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types" / "train"
OUT_DIR      = PROJECT_ROOT / "data" / "datasets" / "processed" / "sofa_types_composited"

CANVAS        = (480, 360)   # width, height
WHITE_LEVEL   = 232          # all channels above this count as backdrop
MIN_BG_SHARE  = 0.25         # skip photos whose border-connected white area is smaller
SEED          = 42


def _foreground_mask(img):
    """Return a 0/255 mask of the sofa, or None if there is no white backdrop."""
    white = np.all(img > WHITE_LEVEL, axis=2).astype(np.uint8)
    n, labels = cv2.connectedComponents(white, connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg = np.isin(labels, [b for b in border if b != 0]) & (white == 1)
    if bg.mean() < MIN_BG_SHARE:
        return None
    fg = (~bg).astype(np.uint8) * 255
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return fg if fg.mean() > 255 * 0.03 else None


def _room(rng):
    """A synthetic room background: gradient wall + floor band + noise."""
    w, h = CANVAS
    horizon = int(h * rng.uniform(0.55, 0.78))
    # Muted, room-like colours: a grey level plus a small tint
    grey = rng.randint(110, 240)
    wall_a = np.clip(np.array([grey + rng.randint(-25, 25) for _ in range(3)], np.float32), 0, 255)
    wall_b = np.clip(wall_a * rng.uniform(0.7, 1.05), 0, 255)
    t = np.linspace(0, 1, horizon, dtype=np.float32)[:, None, None]
    wall = (wall_a * (1 - t) + wall_b * t) * np.ones((1, w, 1), np.float32)

    if rng.random() < 0.6:   # wood-ish (BGR: more red than blue)
        base = rng.randint(50, 170)
        floor_col = np.array([base * 0.55, base * 0.8, base], np.float32)
    else:                    # grey / tiled / carpet
        g = rng.randint(60, 200)
        floor_col = np.array([g + rng.randint(-15, 15) for _ in range(3)], np.float32)
    floor = np.ones((h - horizon, w, 3), np.float32) * floor_col
    if rng.random() < 0.5:  # plank stripes
        for x in range(0, w, rng.randint(25, 60)):
            floor[:, x:x + 2] *= 0.8
    bg = np.concatenate([wall, floor], axis=0)
    bg += np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 6, bg.shape)
    return np.clip(bg, 0, 255).astype(np.uint8), horizon


def _composite(img, mask, rng):
    ys, xs = np.where(mask > 0)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    sofa, m = img[y0:y1, x0:x1], mask[y0:y1, x0:x1]

    bg, horizon = _room(rng)
    w, h = CANVAS
    scale = rng.uniform(0.40, 0.85) * w / sofa.shape[1]
    sw, sh = max(1, int(sofa.shape[1] * scale)), max(1, int(sofa.shape[0] * scale))
    if sh > h * 0.9:
        f = h * 0.9 / sh
        sw, sh = max(1, int(sw * f)), max(1, int(sh * f))
    sofa = cv2.resize(sofa, (sw, sh), interpolation=cv2.INTER_AREA)
    alpha = cv2.GaussianBlur(cv2.resize(m, (sw, sh)), (5, 5), 0).astype(np.float32)[..., None] / 255

    px = rng.randint(0, max(0, w - sw))
    bottom = min(h - 1, horizon + rng.randint(int((h - horizon) * 0.3), int((h - horizon) * 0.9)))
    py = max(0, bottom - sh)
    region = bg[py:py + sh, px:px + sw].astype(np.float32)
    a = alpha[:region.shape[0], :region.shape[1]]
    s = sofa[:region.shape[0], :region.shape[1]].astype(np.float32)
    bg[py:py + sh, px:px + sw] = (s * a + region * (1 - a)).astype(np.uint8)

    tint = np.array([rng.uniform(0.9, 1.1) for _ in range(3)], np.float32)
    return np.clip(bg.astype(np.float32) * tint * rng.uniform(0.75, 1.1), 0, 255).astype(np.uint8)


def main():
    if not IN_DIR.exists():
        raise SystemExit(f"[ERROR] {IN_DIR} not found — run prepare_type_dataset.py first.")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    rng = random.Random(SEED)
    for type_dir in sorted(p for p in IN_DIR.iterdir() if p.is_dir()):
        made = skipped = 0
        (OUT_DIR / type_dir.name).mkdir(parents=True)
        for p in sorted(type_dir.iterdir()):
            img = cv2.imread(str(p))
            mask = _foreground_mask(img) if img is not None else None
            if mask is None:
                skipped += 1
                continue
            out = _composite(img, mask, rng)
            cv2.imwrite(str(OUT_DIR / type_dir.name / f"{p.stem}_room.jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 90])
            made += 1
        print(f"  {type_dir.name:<14} {made:>4} composited, {skipped:>3} skipped (no white backdrop)")
    print(f"Written to {OUT_DIR}")


if __name__ == "__main__":
    main()
