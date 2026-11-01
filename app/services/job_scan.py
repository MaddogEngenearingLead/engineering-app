"""Run the P&ID / scope BOM scan for a job created in the desktop GUI.

Everything runs in-process (no API server needed). The resulting BOM file paths
are written to <uploads>/<job number>.json and the job's job_metadata.json so
the dashboard can link the BOM next to the job.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.file_detector import FileDetector
from app.job_manager import JobManager

logger = logging.getLogger(__name__)


def _store(jm: JobManager, job_number: str, values: dict) -> None:
    """Merge `values` into <uploads>/<job>.json and the job's job_metadata.json."""
    job_file = jm.job_file_path(job_number)
    data = jm._load_json(job_file)
    data.setdefault("job_number", job_number)
    data.update(values)
    job_file.write_text(json.dumps(data, indent=2))

    job_dir, _, _ = jm.get_job_dirs(job_number)
    if job_dir:
        meta = jm._load_metadata(job_dir)
        meta.update(values)
        (job_dir / "job_metadata.json").write_text(json.dumps(meta, indent=2))


def _review_path(jm: JobManager, job_number: str) -> Path:
    job_dir, _, _ = jm.get_job_dirs(job_number)
    out = job_dir / "bom_exports"
    out.mkdir(parents=True, exist_ok=True)
    return out / "review.json"


def load_review(jm: JobManager, job_number: str) -> dict | None:
    """The saved scan + user edits for a job, or None if it was never scanned."""
    try:
        path = _review_path(jm, job_number)
        return json.loads(path.read_text()) if path.is_file() else None
    except Exception:
        return None


def save_review(jm: JobManager, job_number: str, materials: list[dict],
                clarifications: list[str], answers: dict | None = None) -> dict:
    """Store the user's edits and answers and re-export the PDF/JSON/CSV BOM.

    Answered questions are listed as resolved on the BOM and dropped from its
    "needs review" list; unanswered ones stay there.
    """
    from app.services.bom_export import export_all
    from app.services.review_questions import build_questions, record_lines

    review = load_review(jm, job_number)
    if not review:
        raise ValueError("Run the BOM scan first.")
    answers = review.get("answers", {}) if answers is None else answers
    for i, m in enumerate(materials, 1):
        m["item_number"] = i
    result = review["result"]
    job_dir, _, _ = jm.get_job_dirs(job_number)
    questions = build_questions(result.get("flags", []), materials)
    notes = [q["message"] for q in questions
             if q["severity"] in ("warning", "review") and q["id"] not in answers and q["message"]]
    paths = export_all(f"JOB-{job_number}", Path(review["pid_file"]).name, materials,
                       result.get("scope_text", ""), notes, result.get("detected_assets", []),
                       str(job_dir / "bom_exports"), list(clarifications) + record_lines(answers))
    review.update(materials=materials, clarifications=clarifications, answers=answers)
    _review_path(jm, job_number).write_text(json.dumps(review, indent=2, default=str))
    _store(jm, job_number, {"bom_status": "completed", "bom_item_count": len(materials),
                            "bom_generated_at": datetime.now().isoformat(),
                            **{k: str(Path(v).resolve()) for k, v in paths.items()}})
    return paths


def _replay_answers(result: dict, materials: list[dict], old: dict) -> dict:
    """Re-apply earlier answers to a fresh scan so re-generating the BOM keeps them."""
    from app.services.review_questions import apply_answer, build_questions, ensure_uids

    ensure_uids(materials)
    kept = {}
    for q in build_questions(result.get("flags", []), materials):
        prior = old.get(q["id"])
        if prior and prior.get("input") is not None:
            kept[q["id"]] = apply_answer(materials, q, prior["input"])
    return kept


def _run_ai(result: dict, pid_path: str, scope_text: str, materials: list[dict]) -> str:
    """Optional AI second opinion; adds its findings as flags. Never fails the scan."""
    from app.services import ai_review

    if not ai_review.is_enabled():
        return ""
    try:
        review = ai_review.review_with_ai(pid_path, scope_text, materials)
    except Exception as exc:
        logger.warning("AI review skipped: %s", exc)
        result["ai_review"] = {"error": str(exc)}
        return f"AI review was skipped: {exc}"
    result.setdefault("flags", []).extend(review["flags"])
    result["ai_review"] = {k: review[k] for k in ("provider", "model", "summary", "key_page")}
    return f"AI review: {review['summary']}" if review["summary"] else "AI review done."


def run_job_scan(jm: JobManager, job_number: str, demo_pages: list[int] | None = None,
                 new_work_pages: list[int] | None = None) -> dict:
    """Scan the job's P&ID against its scope and generate the BOM.

    Returns a dict with ``status`` of ``completed``, ``needs_clarification`` or
    ``error`` (plus ``message``). Never raises.
    """
    try:
        job_dir, _, _ = jm.get_job_dirs(job_number)
        if not job_dir:
            return {"status": "error", "message": f"Job {job_number} not found."}

        pid_files = jm.get_pid_files(job_number)
        scope_files = jm.get_scope_files(job_number)
        if not pid_files:
            return {"status": "error", "message": "No P&ID file found for this job."}
        if not scope_files:
            return {"status": "error", "message": "No scope file found for this job."}
        pid_path, scope_path = pid_files[0], scope_files[0]

        scope_text = FileDetector().extract_text_from_file(scope_path)
        if not scope_text:
            return {"status": "error",
                    "message": f"Could not read any text from scope file {scope_path.name}."}

        _store(jm, job_number, {"bom_status": "running"})

        from app.services.scope_bom import build_scoped_bom  # heavy import, load lazily

        result = build_scoped_bom(
            str(pid_path),
            scope_text=scope_text,
            demo_pages=demo_pages,
            new_work_pages=new_work_pages,
            job_id=f"JOB-{job_number}",
            source_file=pid_path.name,
            output_dir=str(job_dir / "bom_exports"),
        )

        if result.get("status") != "completed":
            questions = result.get("questions") or []
            message = questions[0].get("message") if questions else "Scan needs clarification."
            _store(jm, job_number, {"bom_status": "needs_clarification", "bom_message": message})
            _review_path(jm, job_number).write_text(json.dumps(
                {"pid_file": str(pid_path.resolve()), "result": result, "materials": [], "clarifications": []},
                indent=2, default=str))
            return {"status": "needs_clarification", "message": message}

        def _p(value):
            return str(Path(value).resolve()) if value else None

        previous = load_review(jm, job_number) or {}
        materials = result.get("materials") or []
        ai_note = _run_ai(result, str(pid_path), scope_text, materials)
        answers = _replay_answers(result, materials, previous.get("answers") or {})
        _review_path(jm, job_number).write_text(json.dumps({
            "pid_file": str(pid_path.resolve()),
            "result": result,
            "materials": materials,
            "clarifications": previous.get("clarifications", []),
            "answers": answers,
        }, indent=2, default=str))

        _store(jm, job_number, {
            "bom_status": "completed",
            "bom_message": None,
            "bom_pdf": _p(result.get("bom_pdf")),
            "bom_json": _p(result.get("bom_json")),
            "bom_csv": _p(result.get("bom_csv")),
            "bom_generated_at": datetime.now().isoformat(),
            "bom_item_count": len(result.get("materials") or []),
        })
        if answers:
            save_review(jm, job_number, materials, previous.get("clarifications", []), answers)
        return {"status": "completed", "message": "BOM generated." + (f" {ai_note}" if ai_note else ""),
                "ai_note": ai_note, "result": result}
    except Exception as exc:  # keep the GUI alive
        logger.exception("BOM scan failed for %s", job_number)
        try:
            _store(jm, job_number, {"bom_status": "error", "bom_message": str(exc)})
        except Exception:
            pass
        return {"status": "error", "message": str(exc)}
