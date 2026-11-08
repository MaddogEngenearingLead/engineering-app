"""
Job Management System

Layout under the uploads folder:

    <uploads>/<JOB NUMBER>.json          <- job file: job number + P&ID path + scope path
    <uploads>/<JOB NUMBER>/pid/          <- copied P&ID file(s)
    <uploads>/<JOB NUMBER>/scope/        <- copied scope file(s)
    <uploads>/<JOB NUMBER>/bom_exports/  <- BOM exports
    <uploads>/<JOB NUMBER>/job_metadata.json

The application resolves the P&ID and scope from the paths stored in
<uploads>/<JOB NUMBER>.json first, then falls back to job_metadata.json,
then to the newest file in the pid/ and scope/ folders.
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
        job_safe = self._sanitize_job_number(job_number)
        job_dir = self.base_dir / job_safe

        pid_dir = job_dir / "pid"
        scope_dir = job_dir / "scope"
        bom_dir = job_dir / "bom_exports"
        for d in (pid_dir, scope_dir, bom_dir):
            d.mkdir(parents=True, exist_ok=True)

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
        (job_dir / "job_metadata.json").write_text(json.dumps(metadata, indent=2))
        logger.info(f"Created job structure for {job_number}: {job_dir}")
        return job_dir, pid_dir, scope_dir, metadata

    def get_job_dirs(self, job_number: str) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
        job_dir = self.base_dir / self._sanitize_job_number(job_number)
        if not job_dir.exists():
            return None, None, None
        return job_dir, job_dir / "pid", job_dir / "scope"

    def get_or_create_job(self, job_number: str) -> Tuple[Path, Path, Path, dict]:
        job_dir, pid_dir, scope_dir = self.get_job_dirs(job_number)
        if job_dir and job_dir.exists():
            pid_dir.mkdir(parents=True, exist_ok=True)
            scope_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "bom_exports").mkdir(parents=True, exist_ok=True)
            return job_dir, pid_dir, scope_dir, self._load_metadata(job_dir)
        return self.create_job(job_number)

    # ------------------------------------------------------------------
    # Metadata / job file helpers
    # ------------------------------------------------------------------

    def job_file_path(self, job_number: str) -> Path:
        """<uploads>/<job number>.json"""
        return self.base_dir / f"{self._sanitize_job_number(job_number)}.json"

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception as e:
                logger.warning(f"Could not load {path}: {e}")
        return {}

    def _load_metadata(self, job_dir: Path) -> dict:
        data = self._load_json(job_dir / "job_metadata.json")
        return data or {"job_dir": str(job_dir.resolve())}

    def _record_path(self, job_number: str, job_dir: Path, key: str, path: Path) -> dict:
        """Record a file path in both the job file and job_metadata.json."""
        metadata = self._load_metadata(job_dir)
        metadata[key] = str(path)
        (job_dir / "job_metadata.json").write_text(json.dumps(metadata, indent=2))

        job_file = self.job_file_path(job_number)
        data = self._load_json(job_file)
        data["job_number"] = job_number
        data[key] = str(path)
        data.setdefault("pid_file", None)
        data.setdefault("scope_file", None)
        job_file.write_text(json.dumps(data, indent=2))
        return metadata

    def _recorded_path(self, job_number: str, key: str) -> Optional[Path]:
        """Path stored for `key`: job file first, then job_metadata.json."""
        value = self._load_json(self.job_file_path(job_number)).get(key)
        if not value:
            job_dir, _, _ = self.get_job_dirs(job_number)
            if job_dir:
                value = self._load_metadata(job_dir).get(key)
        if value and Path(value).is_file():
            return Path(value)
        return None

    def _sanitize_job_number(self, job_number: str) -> str:
        safe = job_number.replace(" ", "-").replace("/", "-").replace("\\", "-")
        safe = "".join(c for c in safe if c.isalnum() or c in "-_")
        return safe or "JOB-UNKNOWN"

    def _sanitize_filename(self, filename: str) -> str:
        for char in ["/", "\\", "..", ":", "*", "?", '"', "<", ">", "|"]:
            filename = filename.replace(char, "_")
        return filename

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_jobs(self) -> list[dict]:
        jobs = []
        if not self.base_dir.exists():
            return jobs
        for job_dir in sorted(self.base_dir.iterdir()):
            meta_file = job_dir / "job_metadata.json"
            if job_dir.is_dir() and meta_file.exists():
                data = self._load_json(meta_file)
                if data:
                    jobs.append(data)
        return jobs

    def delete_job(self, job_number: str) -> None:
        """Permanently remove only this job's directory and dashboard record."""
        job_dir = self.base_dir / self._sanitize_job_number(job_number)
        job_file = self.job_file_path(job_number)
        if job_dir.is_symlink() or job_file.is_symlink():
            raise ValueError("Cannot delete a job through a symbolic link.")
        if not job_dir.is_dir():
            raise FileNotFoundError(f"Job {job_number} was not found.")
        metadata_path = job_dir / "job_metadata.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise ValueError("Job metadata is missing or is a symbolic link.")
        with metadata_path.open(encoding="utf-8") as f:
            metadata = json.load(f)
        if metadata.get("job_number") != job_number:
            raise ValueError("Job number does not match the stored job; deletion was cancelled.")
        if job_file.exists():
            with job_file.open(encoding="utf-8") as f:
                record = json.load(f)
            if record.get("job_number") != job_number:
                raise ValueError("Job record belongs to a different job; deletion was cancelled.")
        shutil.rmtree(job_dir)
        job_file.unlink(missing_ok=True)
        logger.info("Deleted job %s", job_number)

    def get_pid_files(self, job_number: str) -> list[Path]:
        _, pid_dir, _ = self.get_job_dirs(job_number)
        if not pid_dir or not pid_dir.exists():
            return []
        exts = {".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".bmp", ".tiff", ".tif"}
        files = sorted(
            [f for f in pid_dir.iterdir() if f.is_file() and f.suffix.lower() in exts],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        return self._primary_first(files, self._recorded_path(job_number, "pid_file"))

    def get_scope_files(self, job_number: str) -> list[Path]:
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
        job_dir, pid_dir, _, _ = self.get_or_create_job(job_number)
        file_path = pid_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        self._record_path(job_number, job_dir, "pid_file", file_path)
        return file_path

    def save_scope_file(self, job_number: str, filename: str, content: bytes) -> Path:
        job_dir, _, scope_dir, _ = self.get_or_create_job(job_number)
        file_path = scope_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        self._record_path(job_number, job_dir, "scope_file", file_path)
        return file_path

    def add_job_files(self, job_number: str, pid_source: str, scope_source: str | None = None) -> dict:
        """GUI "Create Job": copy the P&ID and scope into the job folders and write
        <uploads>/<job number>.json with their paths. Returns the job file data."""
        pid_src = Path(pid_source)
        scope_src = Path(scope_source) if scope_source else None
        if not pid_src.is_file():
            raise FileNotFoundError(f"P&ID file not found: {pid_source}")
        if scope_src and not scope_src.is_file():
            raise FileNotFoundError(f"Scope file not found: {scope_source}")

        job_dir, pid_dir, scope_dir, _ = self.get_or_create_job(job_number)
        pid_dest = pid_dir / self._sanitize_filename(pid_src.name)
        shutil.copy2(pid_src, pid_dest)

        self._record_path(job_number, job_dir, "pid_file", pid_dest)
        if scope_src:
            scope_dest = scope_dir / self._sanitize_filename(scope_src.name)
            shutil.copy2(scope_src, scope_dest)
            self._record_path(job_number, job_dir, "scope_file", scope_dest)
        data = self._load_json(self.job_file_path(job_number))
        data["job_file"] = str(self.job_file_path(job_number))
        logger.info(f"Job {job_number} created: {self.job_file_path(job_number)}")
        return data

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_job_info(self, job_number: str) -> dict:
        job_dir, pid_dir, scope_dir = self.get_job_dirs(job_number)
        if not job_dir or not job_dir.exists():
            return {"status": "not_found", "job_number": job_number}

        pid_files = self.get_pid_files(job_number)
        scope_files = self.get_scope_files(job_number)
        return {
            "status": "found",
            "job_number": job_number,
            "metadata": self._load_metadata(job_dir),
            "job_file": str(self.job_file_path(job_number)),
            "pid_files": [f.name for f in pid_files],
            "pid_count": len(pid_files),
            "scope_files": [f.name for f in scope_files],
            "scope_count": len(scope_files),
            "pid_dir": str(pid_dir.resolve()) if pid_dir else None,
            "scope_dir": str(scope_dir.resolve()) if scope_dir else None,
        }
