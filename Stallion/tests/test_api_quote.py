"""API tests for /api/quote with the image pipeline and detector stubbed out."""

import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "process_image", lambda *a, **k: {"metadata": {}})
    monkeypatch.setattr(api, "validate_sofa", lambda *a, **k: {
        "predicted_type": "1_seater",
        "confidence": 0.9,
    })
    return TestClient(api.app)


def _post(client, length, width, height, sofa_type="1_seater", image=b"not-a-real-image"):
    data = {"length_mm": length, "width_mm": width, "height_mm": height}
    if sofa_type is not None:
        data["sofa_type"] = sofa_type
    return client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", image, "image/jpeg")},
        data=data,
    )


def test_out_of_range_dimensions_return_400(client):
    resp = _post(client, 3000, 900, 850)  # 3000mm is too long for a 1-seater

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert "1-seater" in body["reason"]


def test_oversized_upload_returns_413(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    resp = _post(client, 850, 850, 850, image=b"x" * 11)

    assert resp.status_code == 413
    assert resp.json()["status"] == "error"


def test_request_ids_are_unique_within_the_same_second():
    ids = {api._next_request_id() for _ in range(100)}
    assert len(ids) == 100


def test_sofa_type_is_required(client):
    resp = _post(client, 850, 850, 850, sofa_type=None)

    assert resp.status_code == 422


def test_user_type_is_priced_and_detector_mismatch_flagged(client):
    resp = _post(client, 2100, 900, 850, sofa_type="3_seater")

    assert resp.status_code == 200
    body = resp.json()
    assert body["sofa_type"] == "3_seater"
    assert body["type_mismatch"] == {"selected": "3_seater", "detected": "1_seater",
                                     "detected_confidence": None}


def test_user_type_matching_detector_is_not_flagged(client):
    resp = _post(client, 850, 850, 850, sofa_type="1-seater")

    assert resp.status_code == 200
    assert resp.json()["type_mismatch"] is None


def test_unknown_user_sofa_type_returns_400(client):
    resp = _post(client, 850, 850, 850, sofa_type="recliner")

    assert resp.status_code == 400


def test_low_confidence_detection_is_not_flagged(client, monkeypatch):
    monkeypatch.setattr(api, "validate_sofa", lambda *a, **k: {
        "predicted_type": "1_seater",
        "type_confidence": api.TYPE_CONFIDENCE_THRESHOLD - 0.1,
    })
    resp = _post(client, 2100, 900, 850, sofa_type="3_seater")

    assert resp.status_code == 200
    assert resp.json()["type_mismatch"] is None


def test_config_lists_type_limits(client):
    types = client.get("/api/config").json()["types"]

    assert types["3_seater"]["width"] == [1800.0, 2400.0]
    assert set(types) == {"1_seater", "2_seater", "3_seater", "4_seater_plus", "l_shape"}


def test_frontend_is_served_with_no_cache(client):
    # Browsers must revalidate so a frontend update shows without a hard refresh
    for path in ("/", "/static/js/main.js", "/static/styles.css"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-cache"


def test_progress_reaches_done(client):
    resp = client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"not-a-real-image", "image/jpeg")},
        data={"length_mm": 850, "width_mm": 850, "height_mm": 850,
              "sofa_type": "1_seater", "progress_id": "test-progress-1234"},
    )
    assert resp.status_code == 200
    assert client.get("/api/progress/test-progress-1234").json()["step"] == "done"


def test_saved_quote_can_be_reopened_and_exported_as_pdf(client):
    request_id = _post(client, 850, 850, 850).json()["request_id"]

    reopened = client.get(f"/api/quotes/{request_id}")
    assert reopened.status_code == 200
    assert reopened.json()["request_id"] == request_id

    pdf = client.get(f"/api/quotes/{request_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    # A full real BOM plus the retail estimate must still fit on one A4 page
    assert len(re.findall(rb"/Type /Page\b(?!s)", pdf.content)) == 1


def test_unknown_or_malformed_quote_id_is_404(client):
    assert client.get("/api/quotes/web_20260101_000000_0000000000000000").status_code == 404
    assert client.get("/api/quotes/..%2F..%2Fsecret").status_code == 404


def test_quote_history_needs_staff_key(client, monkeypatch):
    monkeypatch.setenv("STALLION_STAFF_KEY", "s3cret")
    request_id = _post(client, 850, 850, 850).json()["request_id"]

    assert client.get("/api/quotes").status_code == 403
    assert client.get("/api/quotes", headers={"X-Staff-Key": "wrong"}).status_code == 403
    listed = client.get("/api/quotes", headers={"X-Staff-Key": "s3cret"}).json()["quotes"]
    assert any(q["request_id"] == request_id for q in listed)


def _png_bytes():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 190, 170)).save(buf, format="PNG")
    return buf.getvalue()


def test_detect_type_returns_ui_type_key(client, monkeypatch):
    monkeypatch.setattr(api, "detect_type", lambda path: {
        "sofa_found": True, "sofa_type": "4_seater_plus", "confidence": 0.93, "confident": True})
    resp = client.post("/api/detect-type", files={"image": ("sofa.png", _png_bytes(), "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sofa_type"] == "4_seater_plus" and body["confident"] is True


def test_detect_type_reports_no_sofa(client, monkeypatch):
    monkeypatch.setattr(api, "detect_type", lambda path: {
        "sofa_found": False, "sofa_type": None, "confidence": None, "confident": False})
    body = client.post("/api/detect-type", files={"image": ("x.png", _png_bytes(), "image/png")}).json()
    assert body["sofa_found"] is False and body["sofa_type"] is None


def test_detect_type_rejects_non_images(client, monkeypatch):
    monkeypatch.setattr(api, "detect_type", lambda path: pytest.fail("models must not run"))
    resp = client.post("/api/detect-type", files={"image": ("x.jpg", b"not-a-real-image", "image/jpeg")})
    assert resp.status_code == 400


def test_model_preview_is_a_glb_and_checks_the_range(client):
    ok = client.get("/api/model-preview", params={"sofa_type": "l_shape", "width": 2700, "depth": 975, "height": 850})
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "model/gltf-binary"
    assert ok.content[:4] == b"glTF"
    bad = client.get("/api/model-preview", params={"sofa_type": "1_seater", "width": 2700, "depth": 975, "height": 850})
    assert bad.status_code == 400


def test_model_preview_can_be_exploded(client):
    params = {"sofa_type": "3_seater", "width": 2100, "depth": 900, "height": 850}
    assembled = client.get("/api/model-preview", params=params)
    exploded = client.get("/api/model-preview", params={**params, "exploded": "true"})
    assert exploded.status_code == 200
    assert exploded.content[:4] == b"glTF"
    assert exploded.content != assembled.content


def test_quote_returns_assembled_and_exploded_models(client, isolated_outputs):
    body = _post(client, 2100, 900, 850, sofa_type="3_seater").json()
    for key in ("cad_glb_url", "cad_glb_exploded_url"):
        url = body[key]
        assert url and url.startswith("/outputs/cad/") and url.endswith(".glb"), key
        saved = isolated_outputs / url.removeprefix("/outputs/")
        assert saved.read_bytes()[:4] == b"glTF", key
