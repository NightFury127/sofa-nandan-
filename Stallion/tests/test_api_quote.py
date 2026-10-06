"""API tests for /api/quote with the image pipeline and detector stubbed out."""

import os
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


def _post(client, length, width, height):
    return client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"not-a-real-image", "image/jpeg")},
        data={"length_mm": length, "width_mm": width, "height_mm": height},
    )


def test_out_of_range_dimensions_return_400(client):
    resp = _post(client, 3000, 900, 850)  # 3000mm is too long for a 1-seater

    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert "1-seater" in body["reason"]


def test_oversized_upload_returns_413(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    resp = client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"x" * 11, "image/jpeg")},
        data={"length_mm": 850, "width_mm": 850, "height_mm": 850},
    )

    assert resp.status_code == 413
    assert resp.json()["status"] == "error"


def test_request_ids_are_unique_within_the_same_second():
    ids = {api._next_request_id() for _ in range(100)}
    assert len(ids) == 100


def test_detector_type_used_when_user_picks_none(client):
    resp = _post(client, 850, 850, 850)

    assert resp.status_code == 200
    body = resp.json()
    assert body["sofa_type"] == "1_seater"
    assert body["sofa_type_source"] == "detector"
    assert body["type_mismatch"] is None


def test_user_pick_overrides_detector_and_flags_mismatch(client):
    resp = client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"not-a-real-image", "image/jpeg")},
        data={"length_mm": 2100, "width_mm": 900, "height_mm": 850, "sofa_type": "3_seater"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sofa_type"] == "3_seater"
    assert body["sofa_type_source"] == "user"
    assert body["type_mismatch"] == {"selected": "3_seater", "detected": "1_seater"}


def test_user_pick_matching_detector_is_not_flagged(client):
    resp = client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"not-a-real-image", "image/jpeg")},
        data={"length_mm": 850, "width_mm": 850, "height_mm": 850, "sofa_type": "1-seater"},
    )

    assert resp.json()["type_mismatch"] is None


def test_unknown_user_sofa_type_returns_400(client):
    resp = client.post(
        "/api/quote",
        files={"image": ("sofa.jpg", b"not-a-real-image", "image/jpeg")},
        data={"length_mm": 850, "width_mm": 850, "height_mm": 850, "sofa_type": "recliner"},
    )

    assert resp.status_code == 400
