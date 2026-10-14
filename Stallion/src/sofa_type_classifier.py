"""
sofa_type_classifier.py — Whole-image sofa type classifier.

Wraps data/models/weights/sofa_type_classifier.pt (trained by
train_type_classifier.py). Returns pipeline labels: 1_seater, 2_seater,
3_seater, 4_seater_plus, l_shape.

A model trained on square-padded photos (extend_type_dataset.py) must see
photos padded the same way, or the classifier's centre crop cuts the ends off
wide sofas. Such weights come with a settings file next to them,
sofa_type_classifier.json: {"preprocess": "pad_square"}. Without it, photos
are passed as they are.

The model is loaded once per process and reused.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

WEIGHTS_PATH = Path(__file__).parent.resolve().parent / "data" / "models" / "weights" / "sofa_type_classifier.pt"

_cached = None


def pad_square(img: Image.Image) -> Image.Image:
    """Pad to a square with the photo's own edge colour, so nothing is cropped."""
    a = np.asarray(img)
    edge = tuple(int(v) for v in np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), axis=0))
    w, h = img.size
    return ImageOps.pad(img, (max(w, h),) * 2, color=edge) if w != h else img


class SofaTypeClassifier:
    def __init__(self, weights_path: Path):
        from ultralytics import YOLO
        self._model = YOLO(str(weights_path))
        settings = Path(weights_path).with_suffix(".json")
        self.preprocess = json.loads(settings.read_text())["preprocess"] if settings.exists() else None

    def predict(self, image_path: str):
        """Return (sofa_type, confidence) for the image."""
        return self.predict_ranked(image_path)[0]

    def predict_ranked(self, image_path: str, k: int = 2):
        """The k most likely types, best first: [(sofa_type, confidence), ...]."""
        source = image_path
        if self.preprocess == "pad_square":
            with Image.open(image_path) as im:
                source = np.asarray(pad_square(ImageOps.exif_transpose(im).convert("RGB")))[:, :, ::-1]  # BGR
        probs = self._model(source, verbose=False)[0].probs
        return [(self._model.names[int(i)], round(float(probs.data[int(i)]), 4)) for i in probs.top5[:k]]


def get_type_classifier():
    """Return the shared classifier, or None if no weights have been trained."""
    global _cached
    if _cached is None and WEIGHTS_PATH.exists():
        _cached = SofaTypeClassifier(WEIGHTS_PATH)
    return _cached
