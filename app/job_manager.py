"""
Job Management System

Manages job-scoped file organization:
- Each job gets a unique directory: <uploads>/<JOB NUMBER>/
- P&ID files go in: <uploads>/<JOB NUMBER>/pid/
- Scope files go in: <uploads>/<JOB NUMBER>/scope/
- BOM exports go in: <uploads>/<JOB NUMBER>/bom_exports/
- job_metadata.json records the exact P&ID and scope file paths for the job.

The application (API scan endpoint, GUI) reads the P&ID and scope from the
paths recorded for the job, so a job only needs to be created once.
"""

from pathlib import Path
from typing import Optional, Tuple
import json
import logging
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


class JobManager:
    """Manages job-scoped file organization and metadata."""

    def __init__(self, base_upload_dir: str = "backend/uploads"):
        self.base_dir = Path(base_upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Job creation / lookup
    # ------------------------------------------------------------------

    def create_job(self, job_number: str) -> Tuple[Path, Path, Path, dict]:
        """Create a new job directory structure.

        Returns:
            Tuple of (job_dir, pid_dir, scope_dir, metadata)
        """
        job_safe = self._sanitize_job_number(job_number)
        job_dir = self.base_dir / job_safe

        pid_dir = job_dir / "pid"
        scope_dir = job_dir / "scope"
        bom_dir = job_dir / "bom_exports"

        pid_dir.mkdir(parents=True, exist_ok=True)
        scope_dir.mkdir(parents=True, exist_ok=True)
        bom_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "job_number": job_number,
            "job_safe_name": job_safe,
            "created_at": datetime.now().isoformat(),
            "job_dir": str(job_dir.resolve()),
            "pid_dir": str(pid_dir.resolve()),
            "scope_dir": str(scope_dir.resolve()),
            "bom_dir": str(bom_dir.resolve()),
            "pid_file": None,
            "scope_file": None,
        }
        self._save_metadata(job_dir, metadata)

        logger.info(f"Created job structure for {job_number}: {job_dir}")
        return job_dir, pid_dir, scope_dir, metadata

    def get_job_dirs(self, job_number: str) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
        """Get existing job directories, or (None, None, None) if not found."""
        job_safe = self._sanitize_job_number(job_number)
        job_dir = self.base_dir / job_safe

        if not job_dir.exists():
            return None, None, None

        return job_dir, job_dir / "pid", job_dir / "scope"

    def get_or_create_job(self, job_number: str) -> Tuple[Path, Path, Path, dict]:
        """Get existing job or create new one."""
        job_dir, pid_dir, scope_dir = self.get_job_dirs(job_number)

        if job_dir and job_dir.exists():
            pid_dir.mkdir(parents=True, exist_ok=True)
            scope_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "bom_exports").mkdir(parents=True, exist_ok=True)
            metadata = self._load_metadata(job_dir)
            logger.info(f"Using existing job: {job_number}")
            return job_dir, pid_dir, scope_dir, metadata

        logger.info(f"Job not found, creating new: {job_number}")
        return self.create_job(job_number)

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _load_metadata(self, job_dir: Path) -> dict:
        metadata_file = job_dir / "job_metadata.json"
        if metadata_file.exists():
            try:
                return json.loads(metadata_file.read_text())
            except Exception as e:
                logger.warning(f"Could not load metadata from {metadata_file}: {e}")
        return {"job_dir": str(job_dir.resolve())}

    def _save_metadata(self, job_dir: Path, metadata: dict) -> None:
        (job_dir / "job_metadata.json").write_text(json.dumps(metadata, indent=2))

    def _sanitize_job_number(self, job_number: str) -> str:
        """Sanitize job number for use as directory name."""
        safe = job_number.replace(" ", "-").replace("/", "-").replace("\\", "-")
        safe = "".join(c for c in safe if c.isalnum() or c in "-_")
        return safe or "JOB-UNKNOWN"

    def _sanitize_filename(self, filename: str) -> str:
        """Remove dangerous characters from filename."""
        dangerous_chars = ["/", "\\", "..", ":", "*", "?", '"', "<", ">", "|"]
        sanitized = filename
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "_")
        return sanitized

    def _recorded_path(self, job_number: str, key: str) -> Optional[Path]:
        """Return the file path recorded in job metadata for `key`, if it still exists."""
        job_dir, _, _ = self.get_job_dirs(job_number)
        if not job_dir:
            return None
        value = self._load_metadata(job_dir).get(key)
        if value and Path(value).is_file():
            return Path(value)
        return None

    def _record_path(self, job_dir: Path, key: str, path: Path) -> dict:
        metadata = self._load_metadata(job_dir)
        metadata[key] = str(path.resolve())
        self._save_metadata(job_dir, metadata)
        return metadata

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_jobs(self) -> list[dict]:
        """List all existing jobs (metadata dicts)."""
        jobs = []
        if not self.base_dir.exists():
            return jobs

        for job_dir in sorted(self.base_dir.iterdir()):
            if job_dir.is_dir() and (job_dir / "job_metadata.json").exists():
                try:
                    jobs.append(json.loads((job_dir / "job_metadata.json").read_text()))
                except Exception as e:
                    logger.warning(f"Could not load job metadata from {job_dir}: {e}")

        return jobs

    def get_pid_files(self, job_number: str) -> list[Path]:
        """Get all P&ID files for a job. The file recorded for the job comes first."""
        _, pid_dir, _ = self.get_job_dirs(job_number)
        if not pid_dir or not pid_dir.exists():
            return []

        pid_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".bmp", ".tiff", ".tif"}
        files = sorted(
            [f for f in pid_dir.iterdir() if f.is_file() and f.suffix.lower() in pid_extensions],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        return self._primary_first(files, self._recorded_path(job_number, "pid_file"))

    def get_scope_files(self, job_number: str) -> list[Path]:
        """Get all scope files for a job. The file recorded for the job comes first."""
        _, _, scope_dir = self.get_job_dirs(job_number)
        if not scope_dir or not scope_dir.exists():
            return []

        files = sorted(
            [f for f in scope_dir.iterdir() if f.is_file()],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        return self._primary_first(files, self._recorded_path(job_number, "scope_file"))

    @staticmethod
    def _primary_first(files: list[Path], primary: Optional[Path]) -> list[Path]:
        if not primary:
            return files
        rest = [f for f in files if f.resolve() != primary.resolve()]
        return [primary] + rest

    # ------------------------------------------------------------------
    # Saving files
    # ------------------------------------------------------------------

    def save_pid_file(self, job_number: str, filename: str, content: bytes) -> Path:
        """Save a P&ID file to the job's pid directory and record its path."""
        job_dir, pid_dir, _, _ = self.get_or_create_job(job_number)
        file_path = pid_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        self._record_path(job_dir, "pid_file", file_path)
        logger.info(f"Saved P&ID for {job_number}: {file_path}")
        return file_path

    def save_scope_file(self, job_number: str, filename: str, content: bytes) -> Path:
        """Save a scope file to the job's scope directory and record its path."""
        job_dir, _, scope_dir, _ = self.get_or_create_job(job_number)
        file_path = scope_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        self._record_path(job_dir, "scope_file", file_path)
        logger.info(f"Saved scope for {job_number}: {file_path}")
        return file_path

    def add_job_files(self, job_number: str, pid_source: str, scope_source: str) -> dict:
        """Create the job folder (named by job number) and copy the P&ID and scope
        files into it. Used by the desktop GUI "Create Job" button.

        Returns the updated job metadata (includes `pid_file` and `scope_file`).
        """
        pid_src = Path(pid_source)
        scope_src = Path(scope_source)
        if not pid_src.is_file():
            raise FileNotFoundError(f"P&ID file not found: {pid_source}")
        if not scope_src.is_file():
            raise FileNotFoundError(f"Scope file not found: {scope_source}")

        job_dir, pid_dir, scope_dir, _ = self.get_or_create_job(job_number)

        pid_dest = pid_dir / self._sanitize_filename(pid_src.name)
        scope_dest = scope_dir / self._sanitize_filename(scope_src.name)
        shutil.copy2(pid_src, pid_dest)
        shutil.copy2(scope_src, scope_dest)

        self._record_path(job_dir, "pid_file", pid_dest)
        metadata = self._record_path(job_dir, "scope_file", scope_dest)
        logger.info(f"Job {job_number} created at {job_dir}")
        return metadata

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_job_info(self, job_number: str) -> dict:
        """Get comprehensive job information."""
        job_dir, pid_dir, scope_dir = self.get_job_dirs(job_number)

        if not job_dir or not job_dir.exists():
            return {"status": "not_found", "job_number": job_number}

        metadata = self._load_metadata(job_dir)
        pid_files = self.get_pid_files(job_number)
        scope_files = self.get_scope_files(job_number)

        return {
            "status": "found",
            "job_number": job_number,
            "metadata": metadata,
            "pid_files": [f.name for f in pid_files],
            "pid_count": len(pid_files),
            "scope_files": [f.name for f in scope_files],
            "scope_count": len(scope_files),
            "pid_dir": str(pid_dir.resolve()) if pid_dir else None,
            "scope_dir": str(scope_dir.resolve()) if scope_dir else None,
        }
