from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from tests.pdf_helpers import build_pdf


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _scan(api, pdf, **data):
    with open(pdf, "rb") as f:
        return api.post("/scan", files={"file": ("pid.pdf", f, "application/pdf")}, data=data)


def test_scan_clarification_then_resubmit(api, tmp_path):
    pdf = build_pdf(tmp_path / "pid.pdf", [
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "PI-10"]},
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "TI-11"]},
    ])
    first = _scan(api, pdf).json()
    assert first["status"] == "needs_clarification"
    assert first["candidate_pairs"][0]["pages"] == [1, 2]
    assert "classification_method" in first and "classification_confidence" in first

    second = _scan(api, pdf, demo_pages="1", new_work_pages="[2]").json()
    assert second["status"] == "completed"
    assert second["classification_method"] == "user_input"
    assert second["new_work_pages"] == [2]
    assert second["bom_pdf"] and os.path.exists(second["bom_pdf"])
    assert all("classification_confidence" in f for f in second["flags"])


def test_scan_auto_detects_pages(api, tmp_path):
    pdf = build_pdf(tmp_path / "pid.pdf", [
        {"lines": ["LEGEND"]},
        {"lines": ["TK-1"], "freetext": ["DEMO DRAWING"]},
        {"lines": ["TK-2", "JFSP-1"], "freetext": ["NEW INSTALLATION DRAWING"]},
    ])
    body = _scan(api, pdf).json()
    assert body["status"] == "completed"
    assert body["demo_pages"] == [2] and body["new_work_pages"] == [3]
    assert body["classification_method"] == "freetext"


def test_scan_rejects_bad_parameters(api, tmp_path):
    pdf = build_pdf(tmp_path / "pid.pdf", [{"lines": ["TK-1"]}])
    assert _scan(api, pdf, demo_pages="abc").status_code == 422
    assert _scan(api, pdf, highlight_mapping="[1]").status_code == 422
