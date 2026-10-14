import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import pytest
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
    # The viewer shows what the quote charges for: same springs, clips and legs.
    from bom_geometry import geometry_bom
    from cost_engine import normalize_sofa_type

    for sofa_type, (L, W, H) in SIZES.items():
        scene = build_sofa_mesh({}, {"length_mm": L, "width_mm": W, "height_mm": H}, sofa_type)
        bom = {r["component_group"]: r["new_qty"] for r in geometry_bom(normalize_sofa_type(sofa_type), L, W, H)}
        counts = _layer_counts(scene)
        springs = sum(1 for n in scene.geometry if re.fullmatch(r"springs:(chaise_)?spring_\d+", n))
        assert springs == bom["Springs"], sofa_type
        assert counts["legs"] == bom["Legs"], sofa_type
        clips = sum(1 for n in scene.geometry if "clip" in n)
        assert clips == 2 * bom["Springs"], sofa_type                  # one clip at each end of a spring
        for layer in ("frame", "plywood", "webbing", "padding", "seat_foam", "back_foam", "fabric"):
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


def test_foam_and_timber_in_the_model_are_what_the_quote_prices():
    from bom_geometry import geometry_bom, M3_TO_CFT
    from sofa_interior import layer_of

    scene = build_sofa_mesh({}, {"length_mm": 2100, "width_mm": 900, "height_mm": 850}, "3_seater")
    vol = lambda layer: sum(g.volume for n, g in scene.geometry.items() if layer_of(n) == layer) / 1e9
    bom = {r["component_group"]: r["new_qty"] for r in geometry_bom("3-seater", 2100, 900, 850)}
    assert vol("seat_foam") * 40.0 == pytest.approx(bom["Seat Foam"], rel=1e-3)
    assert vol("back_foam") * 32.0 == pytest.approx(bom["Back Foam"], rel=1e-3)
    assert vol("frame") * M3_TO_CFT == pytest.approx(bom["Wood Frame"], rel=1e-3)


# Generated part -> reference body (data/reference/reference_parts.json). The
# reference draws the arm assembly 90 mm outboard of its shell (#13), so those
# bodies are compared 90 mm further in. Optional 4th value: tolerance in mm
# (#317 is drawn 10 mm shorter at its right end than its left; ours is symmetric).
REFERENCE_MATCHES = [
    ("front_seat_rail", 400, 0), ("bottom_middle_rail", 397, 0), ("bottom_back_rail", 396, 0),
    ("back_top_rail", 410, 0), ("bottom_stretcher_1", 393, 0), ("seat_post_1", 384, 0),
    ("back_post_1", 380, 0), ("stile_block_1", 373, 0), ("back_stile_1", 377, 0),
    ("side_panel_l", 417, 0), ("corner_post_l", 365, 0), ("corner_block_l", 366, 0),
    ("side_rail_low_r", 403, 0), ("side_rail_high_r", 402, 0),
    ("seat_belt_1", 149, 0), ("seat_belt_2", 148, 0), ("back_cross_belt_1", 317, 0, 12), ("back_cross_belt_2", 318, 0),
    ("seat_foam_lower", 312, 0), ("back_cushion", 302, 0), ("front_padding", 309, 0), ("back_cover", 289, 0),
    ("arm_right_inner_bottom_rail", 200, 90), ("arm_right_outer_bottom_rail", 201, 90),
    ("arm_right_outer_top_rail", 209, 90), ("arm_right_inner_mid_rail", 206, 90),
    ("arm_right_inner_top_rail", 207, 90), ("arm_right_top_rail", 208, 90),
    ("arm_right_front_spacer", 202, 90), ("arm_right_back_spacer", 203, 90),
    ("arm_right_end_board_back", 204, 90), ("arm_right_end_board_front", 205, 90),
    ("arm_right_top_foam", 184, 90), ("arm_right_roll", 224, 90),
]


def test_model_at_reference_size_matches_the_reference_parts():
    """At the reference's own size every listed part sits where the Fusion model has it (within 10 mm)."""
    import json
    import numpy as np
    from sofa_build import build_parts

    ref = {r["id"]: r for r in json.loads(
        (Path(__file__).parent.parent / "data" / "reference" / "reference_parts.json").read_text())["solids"]}
    leg = 120.0
    parts = {p.name: p for p in build_parts("3-seater", 2061, 837, 693 + leg)}
    for name, body, shift, *tol in REFERENCE_MATCHES:
        tol = tol[0] if tol else 10
        lo, hi = parts[name].mesh().bounds
        r = ref[body]
        # reference (x, y up, z +front) -> ours (X from the left end, Y from the front, Z up)
        rlo = np.array([r["min"][0] - shift + 1030.5, 423 - r["max"][2], r["min"][1] + leg])
        rhi = np.array([r["max"][0] - shift + 1030.5, 423 - r["min"][2], r["max"][1] + leg])
        assert np.abs(lo - rlo).max() < tol and np.abs(hi - rhi).max() < tol, (name, body, lo - rlo, hi - rhi)


def test_arm_cover_wraps_the_reference_arm():
    # The arm upholstery: shell #13 (813..1030, to 332) plus the sloped top up to the roll at 413 (#17, #184)
    from sofa_build import build_parts
    lo, hi = {p.name: p for p in build_parts("3-seater", 2061, 837, 813)}["arm_right_cover"].mesh().bounds
    assert hi[0] == pytest.approx(2061, abs=1)                # outside face of the arm
    assert lo[0] == pytest.approx(813 + 1030.5 - 8, abs=1)    # inner face, 8 mm over the top foam's lip (#184 at -6)
    assert hi[2] == pytest.approx(413 + 120, abs=3)           # arm top, on 120 mm legs
    assert hi[1] - lo[1] == pytest.approx(823, abs=1)         # #13 depth


def test_reference_spring_layout():
    from sofa_build import build_parts
    parts = build_parts("3-seater", 2061, 837, 813)
    springs = sorted(p.path[:, 0].mean() - 1030.5 for p in parts if p.kind == "wire")
    assert len(springs) == 11                                   # clips #82-#138: 11 positions
    assert springs[0] == pytest.approx(-635, abs=2) and springs[-1] == pytest.approx(635, abs=2)
    assert all(abs(b - a - 127) < 1 for a, b in zip(springs, springs[1:]))


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
