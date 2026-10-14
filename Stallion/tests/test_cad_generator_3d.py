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


def test_glb_parts_have_non_metallic_materials(tmp_path):
    # Without an explicit material glTF defaults to metallic=1, which renders
    # the sofa almost black in the web viewer.
    import json
    import struct

    scene = build_sofa_mesh(make_sample_scaled_bom(), make_sample_dimensions())
    glb = open(export_3d_model(scene, str(tmp_path), "test_request")["glb_path"], "rb").read()
    gltf = json.loads(glb[20:20 + struct.unpack("<I", glb[12:16])[0]])

    for mesh in gltf["meshes"]:
        for prim in mesh["primitives"]:
            material = gltf["materials"][prim["material"]]
            pbr = material["pbrMetallicRoughness"]
            assert pbr["metallicFactor"] == 0.0
            if material["name"] in ("fabric", "seat_foam", "back_foam", "padding"):
                assert max(pbr["baseColorFactor"][:3]) > 0.2     # upholstery not near-black


SIZES = {"1_seater": (850, 850, 850), "2_seater": (1550, 900, 850), "3_seater": (2100, 900, 850),
         "4_seater_plus": (2700, 950, 850), "l_shape": (2700, 975, 850)}


def _layer_counts(scene):
    from collections import Counter
    from sofa_interior import layer_of
    return Counter(layer_of(name) for name in scene.geometry)


def test_interior_model_matches_the_quoted_construction():
    # The viewer shows what the quote charges for: same springs, legs and cushions.
    from bom_geometry import geometry_bom
    from cost_engine import normalize_sofa_type

    for sofa_type, (L, W, H) in SIZES.items():
        scene = build_sofa_mesh({}, {"length_mm": L, "width_mm": W, "height_mm": H}, sofa_type)
        bom = {r["component_group"]: r["new_qty"] for r in geometry_bom(normalize_sofa_type(sofa_type), L, W, H)}
        counts = _layer_counts(scene)
        assert counts["springs"] == bom["Springs"], sofa_type
        assert counts["legs"] == bom["Legs"], sofa_type
        assert counts["seat_foam"] == bom["Sundries"], sofa_type     # one seat cushion per seat
        for layer in ("frame", "plywood", "webbing", "padding", "back_foam", "fabric"):
            assert counts[layer] > 0, (sofa_type, layer)


def test_interior_model_fits_the_quoted_size():
    for sofa_type, (L, W, H) in SIZES.items():
        scene = build_sofa_mesh({}, {"length_mm": L, "width_mm": W, "height_mm": H}, sofa_type)
        lo, hi = scene.bounds
        size = hi - lo
        assert abs(size[0] - L) < 1 and abs(size[2] - H) < 1, sofa_type
        if sofa_type == "l_shape":
            assert size[1] > W                 # chaise reaches forward
        else:
            assert abs(size[1] - W) < 1, sofa_type


def test_seat_foam_volume_matches_the_quote():
    # Foam is drawn inside its 3 mm fabric cover, so it is a few percent under the net quantity.
    from bom_geometry import geometry_bom
    from sofa_interior import layer_of

    scene = build_sofa_mesh({}, {"length_mm": 2100, "width_mm": 900, "height_mm": 850}, "3_seater")
    volume_m3 = sum(g.volume for n, g in scene.geometry.items() if layer_of(n) == "seat_foam") / 1e9
    bom = {r["component_group"]: r["new_qty"] for r in geometry_bom("3-seater", 2100, 900, 850)}
    assert 0.9 < volume_m3 * 40.0 / bom["Seat Foam"] <= 1.0


def test_exploded_model_lifts_the_outer_layers():
    dims = {"length_mm": 2100, "width_mm": 900, "height_mm": 850}
    assembled = build_sofa_mesh({}, dims, "3_seater")
    exploded = build_sofa_mesh({}, dims, "3_seater", exploded=True)
    assert set(assembled.geometry) == set(exploded.geometry)
    assert exploded.bounds[1][2] > assembled.bounds[1][2] * 2
    frame = [n for n in assembled.geometry if n.startswith("frame:")]
    for name in frame:                                   # the frame stays put
        assert (exploded.geometry[name].bounds == assembled.geometry[name].bounds).all()


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
                "sofa_type": "3_seater",
            },
            files={"image": ("sofa.png", png_bytes.tobytes(), "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload.get("cad_step_url") in (None, "")
