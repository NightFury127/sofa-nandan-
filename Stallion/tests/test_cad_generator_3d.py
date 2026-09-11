import os
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cad_generator_3d import build_sofa_mesh, export_3d_model, render_preview_image
from api import app


def make_sample_dimensions():
    return {
        "length_mm": 2400,
        "width_mm": 900,
        "height_mm": 850,
    }


def make_sample_scaled_bom():
    return {
        "wood frame": {"new_qty": 2},
        "plywood": {"new_qty": 2},
        "seat foam": {"new_qty": 1},
        "back foam": {"new_qty": 1},
        "handle foam": {"new_qty": 1},
        "fabric": {"new_qty": 2},
        "springs": {"new_qty": 11},
        "clips": {"new_qty": 45},
        "seat belts": {"new_qty": 3},
        "back rest belts": {"new_qty": 15},
        "legs": {"new_qty": 4},
    }


def test_build_sofa_mesh_returns_non_empty_scene():
    scene = build_sofa_mesh(make_sample_scaled_bom(), make_sample_dimensions())

    assert scene is not None
    assert len(scene.geometry) > 0


def test_export_3d_model_creates_files_on_disk(tmp_path):
    scene = build_sofa_mesh(make_sample_scaled_bom(), make_sample_dimensions())
    result = export_3d_model(scene, str(tmp_path), "test_request")

    assert result["glb_path"].endswith(".glb")
    assert result["obj_path"].endswith(".obj")
    assert os.path.exists(result["glb_path"])
    assert os.path.exists(result["obj_path"])
    assert os.path.getsize(result["glb_path"]) > 0
    assert os.path.getsize(result["obj_path"]) > 0

    preview = render_preview_image(scene, str(tmp_path), "test_request")
    assert os.path.exists(preview)
    assert os.path.getsize(preview) > 0


def test_quote_pipeline_handles_step_generation_failure():
    client = TestClient(app)
    image = np.zeros((300, 300, 3), dtype=np.uint8)
    image[:] = (255, 255, 255)
    _, png_bytes = cv2.imencode(".png", image)

    fake_sofa = {
        "predicted_type": "3_seater",
        "detected_object": "sofa",
        "confidence": 0.99,
        "bbox": [10, 10, 200, 200],
        "analysis_path": "",
        "annotated_image_path": "",
    }

    with patch("api.validate_sofa", return_value=fake_sofa), patch(
        "api.build_sofa_step_model", side_effect=RuntimeError("simulated STEP failure")
    ):
        response = client.post(
            "/api/quote",
            data={
                "customer_name": "Alice",
                "length_mm": 2100,
                "width_mm": 900,
                "height_mm": 850,
            },
            files={"image": ("sofa.png", png_bytes.tobytes(), "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload.get("cad_step_url") in (None, "")
