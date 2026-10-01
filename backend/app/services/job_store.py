from __future__ import annotations

from typing import Any

from pathlib import Path


class PIDJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def add(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._jobs[job_id] = payload
        return payload

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    def latest(self) -> dict[str, Any] | None:
        if not self._jobs:
            return None
        return next(reversed(self._jobs.values()))


JOB_STORE = PIDJobStore()
