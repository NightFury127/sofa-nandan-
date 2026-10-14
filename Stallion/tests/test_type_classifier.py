"""The type classifier wrapper: square padding for models trained on padded photos."""

import json
import os
import sys
import types

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import sofa_type_classifier as stc


def test_pad_square_keeps_the_whole_photo():
    img = Image.new("RGB", (400, 100), (200, 10, 10))
    out = stc.pad_square(img)
    assert out.size == (400, 400)
    a = np.asarray(out)
    assert (a[150:250, :] == (200, 10, 10)).all()          # the photo, uncropped, centred
    assert (a[0, 0] == (200, 10, 10)).all()                # padded with its own edge colour


def _fake_yolo(seen):
    class FakeYOLO:
        names = {0: "3_seater", 1: "l_shape"}

        def __init__(self, path):
            pass

        def __call__(self, source, verbose=False):
            seen.append(source)
            probs = types.SimpleNamespace(data=np.array([0.7, 0.3]), top5=[0, 1])
            return [types.SimpleNamespace(probs=probs)]
    return FakeYOLO


def test_padded_models_get_padded_photos(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=_fake_yolo(seen)))
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"")
    photo = tmp_path / "wide.jpg"
    Image.new("RGB", (300, 100), (10, 120, 10)).save(photo)

    plain = stc.SofaTypeClassifier(weights)
    assert plain.predict(str(photo)) == ("3_seater", 0.7)
    assert seen[-1] == str(photo)                          # passed as is

    weights.with_suffix(".json").write_text(json.dumps({"preprocess": "pad_square"}))
    padded = stc.SofaTypeClassifier(weights)
    assert padded.predict_ranked(str(photo)) == [("3_seater", 0.7), ("l_shape", 0.3)]
    assert seen[-1].shape == (300, 300, 3)                 # padded to a square
