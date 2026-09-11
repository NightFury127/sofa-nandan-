import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_cad import HAS_BUILD123D, build_sofa_step_model, build_sofa_l_shape_modular


def _assert_real_step(path: Path):
    assert path.exists()
    data = path.read_bytes()
    assert len(data) > 500
    head = data[:80].decode("ascii", errors="ignore")
    assert "ISO-10303" in head or "STEP" in head.upper()


def test_step_export_uses_user_dimensions(tmp_path):
    if not HAS_BUILD123D:
        return
    out = tmp_path / "3seater.step"
    result = build_sofa_step_model(
        "3_seater",
        out,
        dimensions={"length_mm": 2100, "width_mm": 900, "height_mm": 850},
    )
    assert result == str(out)
    _assert_real_step(out)


def test_l_shape_step_is_real_cad(tmp_path):
    if not HAS_BUILD123D:
        return
    out = tmp_path / "lshape.step"
    result = build_sofa_l_shape_modular(
        {"sofa_type": "3-seater"},
        {"chaise_length": 1500, "chaise_depth": 1200},
        out,
    )
    assert result == str(out)
    _assert_real_step(out)
