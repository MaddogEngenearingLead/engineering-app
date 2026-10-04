"""
Job Management System

Manages job-scoped file organization:
- Each job gets a unique directory: backend/uploads/JOB-XXXX/
- P&ID files go in: backend/uploads/JOB-XXXX/pid/
- Scope files go in: backend/uploads/JOB-XXXX/scope/
- BOM exports go in: backend/uploads/JOB-XXXX/bom_exports/

Structure:
backend/uploads/
├── JOB-001/
│   ├── pid/
│   │   └── drawing.pdf
│   ├── scope/
│   │   └── scope_of_work.txt
│   └── bom_exports/
│       └── BOM_JOB-001_20261004_150000.pdf
├── JOB-002/
│   ├── pid/
│   ├── scope/
│   └── bom_exports/
└── ...
"""

from pathlib import Path
from typing import Optional, Tuple
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class JobManager:
    """Manages job-scoped file organization and metadata."""

    def __init__(self, base_upload_dir: str = "backend/uploads"):
        """
        Initialize job manager.

        Args:
            base_upload_dir: Base uploads directory (default: backend/uploads)
        """
        self.base_dir = Path(base_upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_job(self, job_number: str) -> Tuple[Path, Path, Path, dict]:
        """
        Create a new job directory structure.

        Args:
            job_number: Job identifier (e.g., "JOB-001", "26-117", etc.)

        Returns:
            Tuple of (job_dir, pid_dir, scope_dir, metadata)
        """
        # Sanitize job number
        job_safe = self._sanitize_job_number(job_number)
        job_dir = self.base_dir / job_safe

        # Create subdirectories
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
        }

        # Save metadata
        metadata_file = job_dir / "job_metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        logger.info(f"Created job structure for {job_number}: {job_dir}")
        return job_dir, pid_dir, scope_dir, metadata

    def get_job_dirs(self, job_number: str) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
        """
        Get existing job directories.

        Args:
            job_number: Job identifier

        Returns:
            Tuple of (job_dir, pid_dir, scope_dir), or (None, None, None) if not found
        """
        job_safe = self._sanitize_job_number(job_number)
        job_dir = self.base_dir / job_safe

        if not job_dir.exists():
            return None, None, None

        pid_dir = job_dir / "pid"
        scope_dir = job_dir / "scope"

        return job_dir, pid_dir, scope_dir

    def get_or_create_job(self, job_number: str) -> Tuple[Path, Path, Path, dict]:
        """
        Get existing job or create new one.

        Args:
            job_number: Job identifier

        Returns:
            Tuple of (job_dir, pid_dir, scope_dir, metadata)
        """
        job_dir, pid_dir, scope_dir = self.get_job_dirs(job_number)

        if job_dir and job_dir.exists():
            metadata = self._load_metadata(job_dir)
            logger.info(f"Using existing job: {job_number}")
            return job_dir, pid_dir, scope_dir, metadata

        logger.info(f"Job not found, creating new: {job_number}")
        return self.create_job(job_number)

    def _load_metadata(self, job_dir: Path) -> dict:
        """Load job metadata from JSON file."""
        metadata_file = job_dir / "job_metadata.json"
        if metadata_file.exists():
            try:
                return json.loads(metadata_file.read_text())
            except Exception as e:
                logger.warning(f"Could not load metadata from {metadata_file}: {e}")
        return {"job_dir": str(job_dir.resolve())}

    def _sanitize_job_number(self, job_number: str) -> str:
        """Sanitize job number for use as directory name."""
        # Replace problematic characters
        safe = job_number.replace(" ", "-").replace("/", "-").replace("\\", "-")
        # Keep only alphanumeric, dash, and underscore
        safe = "".join(c for c in safe if c.isalnum() or c in "-_")
        return safe or "JOB-UNKNOWN"

    def list_jobs(self) -> list[dict]:
        """List all existing jobs.

        Returns:
            List of job metadata dicts
        """
        jobs = []
        if not self.base_dir.exists():
            return jobs

        for job_dir in sorted(self.base_dir.iterdir()):
            if job_dir.is_dir() and (job_dir / "job_metadata.json").exists():
                try:
                    metadata = json.loads((job_dir / "job_metadata.json").read_text())
                    jobs.append(metadata)
                except Exception as e:
                    logger.warning(f"Could not load job metadata from {job_dir}: {e}")

        return jobs

    def get_pid_files(self, job_number: str) -> list[Path]:
        """Get all P&ID files for a job."""
        _, pid_dir, _ = self.get_job_dirs(job_number)
        if not pid_dir or not pid_dir.exists():
            return []

        pid_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".bmp", ".tiff"}
        return sorted(
            [f for f in pid_dir.iterdir() if f.is_file() and f.suffix.lower() in pid_extensions],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

    def get_scope_files(self, job_number: str) -> list[Path]:
        """Get all scope files for a job."""
        _, _, scope_dir = self.get_job_dirs(job_number)
        if not scope_dir or not scope_dir.exists():
            return []

        return sorted(
            [f for f in scope_dir.iterdir() if f.is_file()],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

    def save_pid_file(self, job_number: str, filename: str, content: bytes) -> Path:
        """Save a P&ID file to job's pid directory."""
        _, job_dir, pid_dir, _ = self.get_or_create_job(job_number)
        file_path = pid_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        logger.info(f"Saved P&ID for {job_number}: {file_path}")
        return file_path

    def save_scope_file(self, job_number: str, filename: str, content: bytes) -> Path:
        """Save a scope file to job's scope directory."""
        _, job_dir, _, scope_dir = self.get_or_create_job(job_number)
        file_path = scope_dir / self._sanitize_filename(filename)
        file_path.write_bytes(content)
        logger.info(f"Saved scope for {job_number}: {file_path}")
        return file_path

    def _sanitize_filename(self, filename: str) -> str:
        """Remove dangerous characters from filename."""
        dangerous_chars = ["/", "\\", "..", ":", "*", "?", '"', "<", ">", "|"]
        sanitized = filename
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "_")
        return sanitized

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
