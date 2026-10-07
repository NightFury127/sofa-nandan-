"""
pricing.py — The factory's rate sheet: material rates, wastage, fabric/foam
grades, labour and finishing per sofa type, overhead and profit.

Stored in data/pricing/pricing.json (edited by staff in the web app's rate
editor, or by hand). Every save is validated first, written atomically, and
the previous version is kept as pricing.previous.json.
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

PRICING_PATH = Path(__file__).parent.resolve().parent / "data" / "pricing" / "pricing.json"

SOFA_TYPES = ["1_seater", "2_seater", "3_seater", "4_seater_plus", "l_shape"]
GRADE_GROUPS = ["fabric", "foam"]


class PricingError(ValueError):
    """The rate sheet is missing something or has an invalid value."""


def _number(value, where, lo=0.0, hi=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise PricingError(f"{where} must be a number, got {value!r}")
    if v != v or v < lo or (hi is not None and v > hi):   # v != v catches NaN
        rng = f"between {lo:g} and {hi:g}" if hi is not None else f"at least {lo:g}"
        raise PricingError(f"{where} must be {rng}, got {value!r}")
    return v


def validate_pricing(data: dict) -> dict:
    """Return a cleaned copy of the rate sheet, or raise PricingError."""
    if not isinstance(data, dict):
        raise PricingError("Rate sheet must be a JSON object.")
    out = {"currency": str(data.get("currency", "INR"))[:8],
           "note": str(data.get("note", ""))[:300]}

    materials = data.get("materials")
    if not isinstance(materials, dict) or not materials:
        raise PricingError("Rate sheet needs at least one material.")
    out["materials"] = {}
    for name, m in materials.items():
        if not isinstance(m, dict):
            raise PricingError(f"Material {name!r} must be an object.")
        clean = {
            "unit": str(m.get("unit", ""))[:40],
            "rate": _number(m.get("rate"), f"{name} rate"),
            "wastage_pct": _number(m.get("wastage_pct", 0), f"{name} wastage %", 0, 100),
        }
        group = m.get("grade_group")
        if group:
            if group not in GRADE_GROUPS:
                raise PricingError(f"{name}: unknown grade group {group!r}.")
            clean["grade_group"] = group
        out["materials"][str(name)[:60]] = clean

    grades = data.get("grades") or {}
    out["grades"] = {}
    for group in GRADE_GROUPS:
        options = grades.get(group)
        if not isinstance(options, dict) or "standard" not in options:
            raise PricingError(f"Grades for {group} must include a 'standard' option.")
        out["grades"][group] = {}
        for key, g in options.items():
            key = str(key).strip().lower().replace(" ", "_")[:40]
            out["grades"][group][key] = {
                "label": str(g.get("label") or key)[:60],
                "multiplier": _number(g.get("multiplier"), f"{group} grade {key!r} multiplier", 0.05, 20),
            }

    for field in ("labour_by_type", "finishing_by_type"):
        table = data.get(field) or {}
        out[field] = {t: _number(table.get(t), f"{field.split('_')[0].title()} for {t}") for t in SOFA_TYPES}

    out["overhead_pct"] = _number(data.get("overhead_pct"), "Overhead %", 0, 200)
    out["profit_pct"] = _number(data.get("profit_pct"), "Profit %", 0, 200)
    out["updated_at"] = data.get("updated_at") or datetime.now().isoformat(timespec="seconds")
    return out


def load_pricing(path: Path = None) -> dict:
    path = Path(path or PRICING_PATH)
    with open(path, encoding="utf-8") as f:
        return validate_pricing(json.load(f))


def save_pricing(data: dict, path: Path = None) -> dict:
    """Validate, keep the previous version, then write atomically."""
    path = Path(path or PRICING_PATH)
    clean = validate_pricing({**data, "updated_at": datetime.now().isoformat(timespec="seconds")})
    if path.exists():
        shutil.copy2(path, path.with_name("pricing.previous.json"))
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    os.replace(tmp, path)
    return clean


def ui_type_key(sofa_type: str) -> str:
    """'3-seater' / '3_seater' / '4-seater' -> pricing keys like '3_seater', '4_seater_plus'."""
    key = str(sofa_type).strip().lower().replace("-", "_").replace(" ", "_")
    return {"4_seater": "4_seater_plus", "l_shaped": "l_shape"}.get(key, key)
