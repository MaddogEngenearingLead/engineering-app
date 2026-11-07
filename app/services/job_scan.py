"""Run the P&ID / scope BOM scan for a job created in the desktop GUI.

Everything runs in-process (no API server needed). The resulting BOM file paths
are written to <uploads>/<job number>.json and the job's job_metadata.json so
the dashboard can link the BOM next to the job.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.file_detector import FileDetector
from app.job_manager import JobManager
from app.services.scope_work import create_scope_draft

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


def _clarification_path(jm: JobManager, job_number: str) -> Path:
    return _review_path(jm, job_number).with_name("clarification.json")


def _commit_review(jm: JobManager, job_number: str, review: dict, values: dict,
                   clear_clarification: bool = False) -> None:
    """Restore metadata and review if recording a new generation fails."""
    job_dir, _, _ = jm.get_job_dirs(job_number)
    review_path = _review_path(jm, job_number)
    files = [review_path, jm.job_file_path(job_number), job_dir / "job_metadata.json"]
    if clear_clarification:
        files.append(_clarification_path(jm, job_number))
    originals = {path: path.read_bytes() if path.exists() else None for path in files}
    try:
        review_path.write_text(json.dumps(review, indent=2, default=str))
        _store(jm, job_number, values)
        if clear_clarification:
            _clarification_path(jm, job_number).unlink(missing_ok=True)
    except Exception:
        for path, data in originals.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        raise


def _load_record(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()) if path.is_file() else None
    except Exception:
        return None


def load_current_clarification(jm: JobManager, job_number: str) -> dict | None:
    """Return the latest unresolved scan clarification, including drawing locations."""
    record = _load_record(_clarification_path(jm, job_number))
    if record:
        return record
    legacy = _load_record(_review_path(jm, job_number))
    if legacy and legacy.get("result", {}).get("status") == "needs_clarification":
        return legacy
    return None


def load_completed_review(jm: JobManager, job_number: str) -> dict | None:
    """Return the saved completed scan and its user edits, independently of clarification."""
    return _load_record(_review_path(jm, job_number))


def load_review(jm: JobManager, job_number: str) -> dict | None:
    """Return the current scan issues when clarification is pending, otherwise the saved review."""
    status = jm._load_json(jm.job_file_path(job_number)).get("bom_status")
    if status == "needs_clarification":
        clarification = load_current_clarification(jm, job_number)
        if clarification:
            return clarification
    return load_completed_review(jm, job_number)


def _save_clarification(jm: JobManager, job_number: str, record: dict, message: str) -> None:
    path = _clarification_path(jm, job_number)
    staged = path.with_name(".clarification-" + uuid.uuid4().hex)
    previous = path.read_bytes() if path.exists() else None
    job_dir, _, _ = jm.get_job_dirs(job_number)
    metadata_paths = [jm.job_file_path(job_number), job_dir / "job_metadata.json"]
    metadata = {p: p.read_bytes() if p.exists() else None for p in metadata_paths}
    try:
        staged.write_text(json.dumps(record, indent=2, default=str))
        staged.replace(path)
        _store(jm, job_number, {"bom_status": "needs_clarification", "bom_message": message})
    except Exception:
        for p, content in [(path, previous), *metadata.items()]:
            if content is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(content)
        raise
    finally:
        staged.unlink(missing_ok=True)


def _remaining_old_exports(job_id: str, directory: Path, paths: dict) -> list[str]:
    pattern = re.compile(rf"BOM_{re.escape(job_id)}_\d{{8}}_\d{{6}}(?:_[0-9a-f]{{32}})?\.(?:pdf|json|csv)\Z")
    keep = {Path(paths[key]).name for key in ("bom_pdf", "bom_json", "bom_csv")}
    return sorted(p.name for p in directory.iterdir()
                  if p.name not in keep and pattern.fullmatch(p.name) and p.is_file() and not p.is_symlink())


def _cleanup_warning(job_id: str, directory: Path, paths: dict) -> str:
    remaining = _remaining_old_exports(job_id, directory, paths)
    return ("New BOM was published, but old generated BOM files could not be removed: " + ", ".join(remaining)
            if remaining else "")


def save_review(jm: JobManager, job_number: str, materials: list[dict],
                clarifications: list[str], answers: dict | None = None) -> dict:
    """Store the user's edits and answers and re-export the PDF/JSON/CSV BOM.

    Answered questions are listed as resolved on the BOM and dropped from its
    "needs review" list; unanswered ones stay there.
    """
    from app.services.bom_export import export_all, job_export_id, publish_job_exports, staged_job_exports
    from app.services.review_questions import build_questions, record_lines

    review = load_completed_review(jm, job_number)
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
    job_id = job_export_id(job_number)
    output_dir = job_dir / "bom_exports"
    with staged_job_exports(str(output_dir)) as stage:
        staged = export_all(job_id, Path(review["pid_file"]).name, materials,
                            result.get("scope_text", ""), notes, result.get("detected_assets", []),
                            str(stage), list(clarifications) + record_lines(answers))
        review.update(materials=materials, clarifications=clarifications, answers=answers)
        def commit(paths):
            review["result"].update(paths)
            _commit_review(jm, job_number, review,
                           {"bom_status": "completed", "bom_message": None, "bom_item_count": len(materials),
                            "bom_generated_at": datetime.now().isoformat(), **paths})
        paths = publish_job_exports(job_id, stage, staged, str(output_dir), commit=commit)
    warning = _cleanup_warning(job_id, output_dir, paths)
    if warning:
        _store(jm, job_number, {"bom_message": warning})
        raise RuntimeError(warning)
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
        pid_path = pid_files[0]

        # The scope is optional; without one the scan relies on the P&ID itself.
        scope_text = ""
        if scope_files:
            scope_text = FileDetector().extract_text_from_file(scope_files[0]) or ""
            if not scope_text:
                return {"status": "error",
                        "message": f"Could not read any text from scope file {scope_files[0].name}."}

        _store(jm, job_number, {"bom_status": "running"})

        from app.services.scope_bom import build_scoped_bom  # heavy import, load lazily
        from app.services.bom_export import export_all, job_export_id, publish_job_exports, staged_job_exports
        from app.services.review_questions import build_questions, record_lines

        output_dir = job_dir / "bom_exports"
        job_id = job_export_id(job_number)
        with staged_job_exports(str(output_dir)) as stage:
            result = build_scoped_bom(
                str(pid_path), scope_text=scope_text, demo_pages=demo_pages,
                new_work_pages=new_work_pages, job_id=job_id, source_file=pid_path.name,
                output_dir=str(stage),
            )

            if result.get("status") not in ("completed", "needs_clarification"):
                raise ValueError(result.get("message") or "BOM scan failed")
            if result.get("status") == "needs_clarification":
                questions = result.get("questions") or []
                message = questions[0].get("message") if questions else "Scan needs clarification."
                _save_clarification(jm, job_number,
                                    {"pid_file": str(pid_path.resolve()), "result": result,
                                     "materials": [], "clarifications": []}, message)
                return {"status": "needs_clarification", "message": message}

            if not scope_files:
                draft = create_scope_draft(jm, job_number, pid_path, result)
                _store(jm, job_number, {"bom_status": "needs_scope_review",
                                        "bom_message": "Review the proposed scope before continuing."})
                return {"status": "needs_scope_review", "message": "Review the proposed scope before continuing.",
                        "draft": draft}

            # Validate the initial scan even when replaying answers requires re-export.
            previous = load_completed_review(jm, job_number) or {}
            materials = result.get("materials") or []
            ai_note = _run_ai(result, str(pid_path), scope_text, materials)
            answers = _replay_answers(result, materials, previous.get("answers") or {})
            if answers or previous.get("clarifications"):
                # First ensure the scan did not silently report an export failure.
                if not all(result.get(k) for k in ("bom_pdf", "bom_json", "bom_csv")):
                    raise ValueError("Scan did not produce all BOM exports")
                questions = build_questions(result.get("flags", []), materials)
                notes = [q["message"] for q in questions
                         if q["severity"] in ("warning", "review") and q["id"] not in answers and q["message"]]
                result.update(export_all(job_id, pid_path.name, materials, result.get("scope_text", ""),
                                         notes, result.get("detected_assets", []), str(stage),
                                         list(previous.get("clarifications", [])) + record_lines(answers)))
            def commit(paths):
                result.update(paths)
                _commit_review(jm, job_number, {
                    "pid_file": str(pid_path.resolve()), "result": result, "materials": materials,
                    "clarifications": previous.get("clarifications", []), "answers": answers,
                }, {
                    "bom_status": "completed", "bom_message": None, **paths,
                    "bom_generated_at": datetime.now().isoformat(), "bom_item_count": len(materials),
                }, clear_clarification=True)
            publish_job_exports(job_id, stage, result, str(output_dir), commit=commit)
        warning = _cleanup_warning(job_id, output_dir, result)
        if warning:
            _store(jm, job_number, {"bom_status": "error", "bom_message": warning})
            return {"status": "error", "message": warning, "result": result}
        return {"status": "completed", "message": "BOM generated." + (f" {ai_note}" if ai_note else ""),
                "ai_note": ai_note, "result": result}
    except Exception as exc:  # keep the GUI alive
        logger.exception("BOM scan failed for %s", job_number)
        try:
            _store(jm, job_number, {"bom_status": "error", "bom_message": str(exc)})
        except Exception:
            pass
        return {"status": "error", "message": str(exc)}
