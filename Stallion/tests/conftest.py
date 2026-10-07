"""Shared test setup."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def isolated_outputs(tmp_path, monkeypatch):
    """
    Point the API's output folder at a temp dir, so test quotes don't land in
    outputs/requests and show up in the real quote history.
    """
    import api

    outputs = tmp_path / "outputs"
    (outputs / "cad").mkdir(parents=True)
    monkeypatch.setattr(api, "OUTPUTS_DIR", outputs)
    return outputs
