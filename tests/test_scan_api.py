from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.chdir(tmp_path)


def _post(path, **data):
    with open(path, "rb") as f:
        return client.post(f"{settings.api_prefix}/scan", files={"file": ("p.pdf", f, "application/pdf")}, data=data)


def test_scan_completed(freetext_pdf):
    r = _post(freetext_pdf, scope_of_work="Replace TK-1")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["demo_pages"] == [2] and body["new_work_pages"] == [3]
    assert os.path.exists(body["bom_pdf"])


def test_clarify_and_resubmit(ambiguous_pdf):
    first = _post(ambiguous_pdf).json()
    assert first["status"] == "needs_clarification"
    pair = first["questions"][0]["candidate_pairs"][0]["pages"]
    second = _post(ambiguous_pdf, demo_pages=str(pair[0]), new_work_pages=str(pair[1])).json()
    assert second["status"] == "completed"
    assert second["classification_method"] == "user_override"
    third = _post(ambiguous_pdf, highlight_mapping=json.dumps({"red": "demo", "green": "new_work"})).json()
    assert third["status"] == "completed"


def test_bad_parameters(freetext_pdf):
    assert _post(freetext_pdf, demo_pages="a,b").status_code == 400
    assert _post(freetext_pdf, highlight_mapping="[1]").status_code == 400


def test_scope_bom_endpoint_removed(freetext_pdf):
    assert client.post(f"{settings.api_prefix}/scope-bom").status_code == 404
