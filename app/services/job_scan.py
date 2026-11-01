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


def run_job_scan(jm: JobManager, job_number: str) -> dict:
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
            job_id=f"JOB-{job_number}",
            source_file=pid_path.name,
            output_dir=str(job_dir / "bom_exports"),
        )

        if result.get("status") != "completed":
            questions = result.get("questions") or []
            message = questions[0].get("message") if questions else "Scan needs clarification."
            _store(jm, job_number, {"bom_status": "needs_clarification", "bom_message": message})
            return {"status": "needs_clarification", "message": message}

        def _p(value):
            return str(Path(value).resolve()) if value else None

        _store(jm, job_number, {
            "bom_status": "completed",
            "bom_message": None,
            "bom_pdf": _p(result.get("bom_pdf")),
            "bom_json": _p(result.get("bom_json")),
            "bom_csv": _p(result.get("bom_csv")),
            "bom_generated_at": datetime.now().isoformat(),
            "bom_item_count": len(result.get("materials") or []),
        })
        return {"status": "completed", "message": "BOM generated.", "result": result}
    except Exception as exc:  # keep the GUI alive
        logger.exception("BOM scan failed for %s", job_number)
        try:
            _store(jm, job_number, {"bom_status": "error", "bom_message": str(exc)})
        except Exception:
            pass
        return {"status": "error", "message": str(exc)}
