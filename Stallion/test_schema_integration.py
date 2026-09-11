"""Quick integration smoke-test for schema-driven cost engine and CAD generator."""
import sys
sys.path.insert(0, 'src')

from cost_engine import SofaCostEngine, _SCHEMA_AVAILABLE
from cad_generator_3d import build_sofa_mesh, _lookup_qty, _LEGACY_TO_SCHEMA

# ── Test 1: generate_quote_from_schema for all sofa types ───────────────────
print("=== Test 1: generate_quote_from_schema ===")
assert _SCHEMA_AVAILABLE, "component_schema_extended not importable"

engine = SofaCostEngine()
cases = [
    ("1-seater", 850,  800,  800),
    ("2-seater", 1500, 900,  850),
    ("3-seater", 2100, 900,  850),
    ("4-seater", 2700, 950,  850),
    ("l-shape",  2800, 1000, 850),
]
prices = []
for sofa_type, L, W, H in cases:
    result = engine.generate_quote_from_schema(L, W, H, sofa_type=sofa_type, output_prefix="schema_test")
    price = result["summary"]["final_quotation_price"]
    prices.append(price)
    assert price > 0, f"Expected positive price for {sofa_type}, got {price}"
    assert result["source"] == "component_schema_extended"
    print(f"  {sofa_type:12}: INR {price:,.0f}")

# Prices should increase monotonically with sofa size
for i in range(len(prices) - 1):
    assert prices[i] < prices[i + 1], (
        f"Price not monotonic: {cases[i][0]}={prices[i]:.0f} >= "
        f"{cases[i+1][0]}={prices[i+1]:.0f}"
    )
print("  -> Monotonically increasing: OK")

# ── Test 2: legacy BOM names still work in build_sofa_mesh ──────────────────
print("\n=== Test 2: build_sofa_mesh with legacy BOM names ===")
legacy_bom = {
    "wood frame": {"new_qty": 6},
    "plywood": {"new_qty": 2},
    "seat foam": {"new_qty": 12},
    "back foam": {"new_qty": 7.5},
    "handle foam": {"new_qty": 1},
    "fabric": {"new_qty": 10},
    "springs": {"new_qty": 20},
    "legs": {"new_qty": 4},
}
dims = {"length_mm": 2100, "width_mm": 900, "height_mm": 850}
scene = build_sofa_mesh(legacy_bom, dims)
assert len(scene.geometry) > 0, "Legacy BOM produced empty scene"
print(f"  geometry pieces: {len(scene.geometry)}  -> OK")

# ── Test 3: schema BOM (component IDs as keys) works in build_sofa_mesh ─────
print("\n=== Test 3: build_sofa_mesh with schema component IDs ===")
schema_bom = {
    "seat_rail_front": {"new_qty": 2.1},
    "seat_deck_board": {"new_qty": 1.6},
    "seat_foam":       {"new_qty": 12.0},
    "back_foam":       {"new_qty": 7.5},
    "handle_foam":     {"new_qty": 1.0},
    "fabric_seat":     {"new_qty": 4.4},
    "spring_unit":     {"new_qty": 20.0},
    "leg":             {"new_qty": 4.0},
    "handle_frame":    {"new_qty": 2.0},
}
scene2 = build_sofa_mesh(schema_bom, dims)
assert len(scene2.geometry) > 0, "Schema BOM produced empty scene"
print(f"  geometry pieces: {len(scene2.geometry)}  -> OK")

# ── Test 4: _lookup_qty resolves aliases correctly ───────────────────────────
print("\n=== Test 4: _lookup_qty alias resolution ===")
# Legacy name -> value present with legacy key
assert _lookup_qty(legacy_bom, "legs") == 4.0
assert _lookup_qty(legacy_bom, "seat foam") == 12.0
# Schema ID -> value present with legacy key (reverse alias)
assert _lookup_qty(legacy_bom, "leg") == 4.0
assert _lookup_qty(legacy_bom, "seat_foam") == 12.0
# Schema key -> value present with schema ID key
assert _lookup_qty(schema_bom, "legs") == 4.0
assert _lookup_qty(schema_bom, "seat foam") == 12.0
print("  -> All alias lookups: OK")

print("\n=== All integration tests PASSED ===")
