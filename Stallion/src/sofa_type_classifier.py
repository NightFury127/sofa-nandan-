"""
sofa_type_classifier.py — Whole-image sofa type classifier.

Wraps data/models/weights/sofa_type_classifier.pt (trained by
train_type_classifier.py). Returns pipeline labels: 1_seater, 2_seater,
3_seater, l_shape. It cannot predict 4_seater_plus (too few training photos).

The model is loaded once per process and reused.
"""

from pathlib import Path

WEIGHTS_PATH = Path(__file__).parent.resolve().parent / "data" / "models" / "weights" / "sofa_type_classifier.pt"

_cached = None


class SofaTypeClassifier:
    def __init__(self, weights_path: Path):
        from ultralytics import YOLO
        self._model = YOLO(str(weights_path))

    def predict(self, image_path: str):
        """Return (sofa_type, confidence) for the image."""
        probs = self._model(image_path, verbose=False)[0].probs
        return self._model.names[int(probs.top1)], round(float(probs.top1conf), 4)


def get_type_classifier():
    """Return the shared classifier, or None if no weights have been trained."""
    global _cached
    if _cached is None and WEIGHTS_PATH.exists():
        _cached = SofaTypeClassifier(WEIGHTS_PATH)
    return _cached
