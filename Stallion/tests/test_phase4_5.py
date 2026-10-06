"""Pytest suite for Stallion Phase 4 and Phase 5 validation."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cost_engine import SofaCostEngine


def _make_engine():
    engine = SofaCostEngine()
    engine.load_data()
    return engine


def test_phase4_dimension_limits():
    engine = _make_engine()

    valid_cases = [
        (850, 800, 800, "1-seater"),
        (1500, 900, 850, "2-seater"),
        (2100, 900, 850, "3-seater"),
        (2700, 950, 850, "4-seater"),
        (2800, 1000, 850, "l-shape"),
    ]
    for length, width, height, sofa_type in valid_cases:
        engine.generate_quote(length, width, height, sofa_type=sofa_type, output_prefix="test")

    invalid_cases = [
        (1200, 800, 800, "1-seater"),
        (500, 900, 850, "2-seater"),
        (2100, 600, 850, "3-seater"),
        (2700, 950, 600, "4-seater"),
        (4000, 1000, 850, "l-shape"),
    ]
    for length, width, height, sofa_type in invalid_cases:
        with pytest.raises(ValueError):
            engine.generate_quote(length, width, height, sofa_type=sofa_type, output_prefix="test")


def test_phase4_bom_scaling_per_sofa_type():
    engine = _make_engine()

    for sofa_type, length, width, height in [
        ("1-seater", 850, 800, 800),
        ("2-seater", 1500, 900, 850),
        ("3-seater", 2100, 900, 850),
        ("4-seater", 2700, 950, 850),
        ("l-shape", 2800, 1000, 850),
    ]:
        _, bom_df = engine.generate_scaled_bom(length, width, height, sofa_type=sofa_type)
        assert not bom_df.empty
        _, summary = engine.compute_cost(bom_df)
        assert summary["final_quotation_price"] > 0


@pytest.mark.parametrize("detector_label, canonical", [
    ("1_seater", "1-seater"),
    ("2_seater", "2-seater"),
    ("3_seater", "3-seater"),
    ("4_seater_plus", "4-seater"),
    ("l_shape", "l-shape"),
])
def test_detector_labels_price_like_canonical_types(detector_label, canonical):
    engine = _make_engine()
    L0, W0, H0 = engine.TYPE_BASE_DIMS[canonical]

    _, bom_detector = engine.generate_scaled_bom(L0, W0, H0, sofa_type=detector_label)
    _, bom_canonical = engine.generate_scaled_bom(L0, W0, H0, sofa_type=canonical)
    _, summary_detector = engine.compute_cost(bom_detector)
    _, summary_canonical = engine.compute_cost(bom_canonical)

    assert summary_detector == summary_canonical


def test_detector_labels_enforce_dimension_limits():
    engine = _make_engine()
    with pytest.raises(ValueError):
        engine.generate_scaled_bom(100, 100, 100, sofa_type="3_seater")


def test_unknown_sofa_type_is_rejected():
    engine = _make_engine()
    with pytest.raises(ValueError):
        engine.generate_scaled_bom(2100, 900, 850, sofa_type="recliner")


def test_phase5_generates_fusion_json(tmp_path):
    test_request = {
        "request_id": "fusion_test_001",
        "customer_name": "Test Customer",
        "sofa_type": "3_seater",
        "image_path": "test_image.jpg",
        "dimensions_mm": {
            "length": 2100,
            "width": 900,
            "height": 850,
        },
    }

    target_path = tmp_path / "fusion_test_001_input_request.json"
    target_path.write_text(json.dumps(test_request, indent=4), encoding="utf-8")

    assert target_path.exists()
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    assert payload["dimensions_mm"]["length"] == 2100
