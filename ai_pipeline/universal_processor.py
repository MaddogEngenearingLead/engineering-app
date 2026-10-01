from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_pipeline.pipeline import process_pid_file
from ai_pipeline.pdf_pipeline import process_pdf_pid_file


def process_pid_file_universal(file_path: str) -> dict[str, Any]:
    """Universal entry point that routes to the appropriate processor based on file type."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_ext = path.suffix.lower()

    if file_ext == ".pdf":
        return process_pdf_pid_file(file_path)
    elif file_ext in {".png", ".jpg", ".jpeg", ".gif"}:
        return process_pid_file(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_ext}. Supported types: .pdf, .png, .jpg, .jpeg, .gif")
