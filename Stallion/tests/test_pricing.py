"""Rate sheet, wastage, grades, labour per type and the pricing/size endpoints."""

import json
import os
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import api
import pricing
from cost_engine import SofaCostEngine


def _cost(sofa_type, L, W, H, **grades):
    e = SofaCostEngine()
    e.load_data()
    _, bom = e.generate_scaled_bom(L, W, H, sofa_type)
    return e.compute_cost(bom, sofa_type, **grades)


def _qty(cost_df, name, col="net_qty"):
    return float(cost_df.loc[cost_df["component_group"] == name, col].iloc[0])


def test_back_foam_follows_height_and_seat_foam_follows_depth():
    base, _ = _cost("3-seater", 2100, 900, 850)
    taller, _ = _cost("3-seater", 2100, 900, 935)
    deeper, _ = _cost("3-seater", 2100, 990, 850)

    assert _qty(taller, "Back Foam") > _qty(base, "Back Foam")
    assert _qty(deeper, "Back Foam") == pytest.approx(_qty(base, "Back Foam"))
    assert _qty(deeper, "Seat Foam") > _qty(base, "Seat Foam")
    assert _qty(taller, "Seat Foam") == pytest.approx(_qty(base, "Seat Foam"))


def test_plywood_responds_to_depth():
    base, _ = _cost("3-seater", 2100, 900, 850)
    deeper, _ = _cost("3-seater", 2100, 990, 850)
    assert _qty(deeper, "Plywood") > _qty(base, "Plywood")


def test_whole_unit_items_are_rounded_up():
    cost, _ = _cost("3-seater", 2310, 900, 850)
    for name in ("Springs", "Legs", "Sundries"):
        assert _qty(cost, name, "new_qty") == int(_qty(cost, name, "new_qty"))


def test_geometry_quantities_match_industry_rules_of_thumb():
    # Standard 3-seater: Indian makers use ~10-12 m of 54" fabric and
    # 10-15 kg of foam; a 6" 40D seat over 3 seats is ~7-9 kg.
    cost, _ = _cost("3-seater", 2100, 900, 850)
    assert 9 <= _qty(cost, "Fabric") <= 13
    assert 7 <= _qty(cost, "Seat Foam") <= 9
    assert 10 <= sum(_qty(cost, n) for n in ("Seat Foam", "Back Foam", "Padding Foam")) <= 15
    assert _qty(cost, "Sundries") == 3          # one kit per seat


def test_bigger_sofas_need_more_material_and_cost_more():
    small, s_sum = _cost("3-seater", 1900, 900, 850)
    large, l_sum = _cost("3-seater", 2400, 900, 850)
    for name in ("Wood Frame", "Fabric", "Seat Foam", "Springs"):
        assert _qty(large, name) > _qty(small, name)
    assert l_sum["final_quotation_price"] > s_sum["final_quotation_price"]
    _, l_shape = _cost("l-shape", 2700, 975, 850)
    _, four = _cost("4-seater", 2700, 950, 850)
    assert l_shape["material_cost"] > four["material_cost"]


def test_retail_price_adds_dealer_markup_then_gst():
    _, s = _cost("3-seater", 2100, 900, 850)
    sheet = pricing.load_pricing()
    retail = s["final_quotation_price"] * (1 + sheet["dealer_markup_pct"] / 100)
    assert s["retail_price_excl_gst"] == pytest.approx(retail)
    assert s["retail_gst"] == pytest.approx(retail * sheet["gst_pct"] / 100)
    assert s["retail_price_incl_gst"] == pytest.approx(retail * (1 + sheet["gst_pct"] / 100))


def test_rate_sheet_without_retail_fields_gets_defaults():
    sheet = pricing.load_pricing()
    for field in ("dealer_markup_pct", "gst_pct"):
        sheet.pop(field)
    clean = pricing.validate_pricing(sheet)
    assert clean["dealer_markup_pct"] == 40 and clean["gst_pct"] == 18


def test_wastage_is_added_to_order_quantity():
    cost, _ = _cost("3-seater", 2100, 900, 850)
    rate_sheet = pricing.load_pricing()
    w = rate_sheet["materials"]["Fabric"]["wastage_pct"]
    assert _qty(cost, "Fabric", "new_qty") == pytest.approx(_qty(cost, "Fabric") * (1 + w / 100))


def test_labour_is_per_type():
    _, one = _cost("1-seater", 850, 850, 850)
    _, three = _cost("3-seater", 2100, 900, 850)
    rate_sheet = pricing.load_pricing()
    assert one["labor_cost"] == rate_sheet["labour_by_type"]["1_seater"]
    assert three["labor_cost"] == rate_sheet["labour_by_type"]["3_seater"]


def test_grades_change_the_price_and_unknown_grade_is_rejected():
    _, standard = _cost("3-seater", 2100, 900, 850)
    _, premium = _cost("3-seater", 2100, 900, 850, fabric_grade="premium")
    assert premium["final_quotation_price"] > standard["final_quotation_price"]
    with pytest.raises(ValueError):
        _cost("3-seater", 2100, 900, 850, fabric_grade="gold")


@pytest.mark.parametrize("bad", [
    {"profit_pct": -5},
    {"overhead_pct": "abc"},
    {"grades": {"fabric": {"premium": {"label": "P", "multiplier": 2}}, "foam": {"standard": {"label": "S", "multiplier": 1}}}},
])
def test_invalid_rate_sheets_are_rejected(bad):
    sheet = pricing.load_pricing()
    sheet.update(bad)
    with pytest.raises(pricing.PricingError):
        pricing.validate_pricing(sheet)


@pytest.fixture
def staff_client(tmp_path, monkeypatch):
    path = tmp_path / "pricing.json"
    shutil.copy2(pricing.PRICING_PATH, path)
    monkeypatch.setattr(pricing, "PRICING_PATH", path)
    monkeypatch.setenv("STALLION_STAFF_KEY", "s3cret")
    return TestClient(api.app), path


def test_rate_editor_saves_and_keeps_previous_version(staff_client):
    client, path = staff_client
    headers = {"X-Staff-Key": "s3cret"}
    sheet = client.get("/api/pricing", headers=headers).json()
    sheet["materials"]["Fabric"]["rate"] = 999

    resp = client.put("/api/pricing", json=sheet, headers=headers)
    assert resp.status_code == 200
    assert json.loads(path.read_text())["materials"]["Fabric"]["rate"] == 999
    assert path.with_name("pricing.previous.json").exists()


def test_rate_editor_requires_staff_key_and_valid_values(staff_client):
    client, _ = staff_client
    assert client.get("/api/pricing").status_code == 403
    sheet = client.get("/api/pricing", headers={"X-Staff-Key": "s3cret"}).json()
    assert client.put("/api/pricing", json=sheet).status_code == 403
    sheet["profit_pct"] = -1
    resp = client.put("/api/pricing", json=sheet, headers={"X-Staff-Key": "s3cret"})
    assert resp.status_code == 400 and "Profit" in resp.json()["reason"]


def test_size_options_compare_prices_and_flag_out_of_range():
    client = TestClient(api.app)
    data = client.get("/api/size-options", params={
        "sofa_type": "3_seater", "width": 2350, "depth": 900, "height": 850}).json()

    by_label = {o["label"]: o for o in data["options"]}
    assert by_label["Width −100 mm"]["difference"] < 0
    assert by_label["Width +100 mm"]["price"] is None          # 2450 > 2400 max
    assert "out of bounds" in by_label["Width +100 mm"]["reason"]


def test_config_lists_grades():
    grades = TestClient(api.app).get("/api/config").json()["grades"]
    assert {g["key"] for g in grades["fabric"]} >= {"standard", "premium"}


def test_pdf_includes_a_webp_photo_and_fits_one_page(tmp_path):
    from PIL import Image
    from quote_pdf import build_quote_pdf

    Image.new("RGB", (400, 300), (120, 120, 120)).save(tmp_path / "original_image.webp")
    (tmp_path / "response.json").write_text(json.dumps({
        "request_id": "web_20260101_000000_0123456789abcdef", "customer_name": "Test",
        "sofa_type": "3_seater", "dimensions_mm": {"length": 2100, "width": 900, "height": 850},
        "quote": {"material_cost": 1, "final_quotation_price": 2,
                  "fabric_grade_label": "Premium fabric", "foam_grade_label": "Standard foam"},
        "bom": [{"component": f"Part {i}", "qty": 1, "unit": "pieces", "unit_cost": 1, "total_cost": 1} for i in range(10)],
    }))
    pdf = build_quote_pdf(tmp_path)

    assert pdf.count(b"/Subtype /Image") >= 1          # the photo was embedded
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page>") + pdf.count(b"/Type /Page ") >= 1
    assert b"/Count 1" in pdf                             # one page
