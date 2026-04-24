from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import AppPaths


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


class JobStore:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def load(self) -> dict[str, Any]:
        return _read_json(self.paths.jobs_path, {"jobs": []})

    def save(self, payload: dict[str, Any]) -> None:
        self.paths.ensure()
        _atomic_write_json(self.paths.jobs_path, payload)

    def list_jobs(self) -> list[dict[str, Any]]:
        return sorted(self.load()["jobs"], key=lambda job: job.get("created_at", ""))

    def get(self, job_id: str) -> dict[str, Any] | None:
        for job in self.load()["jobs"]:
            if job.get("id") == job_id:
                return job
        return None

    def add(self, job: dict[str, Any]) -> None:
        payload = self.load()
        payload["jobs"].append(job)
        self.save(payload)

    def update(self, job: dict[str, Any]) -> None:
        payload = self.load()
        for index, existing in enumerate(payload["jobs"]):
            if existing.get("id") == job.get("id"):
                job["updated_at"] = utc_now_iso()
                payload["jobs"][index] = job
                self.save(payload)
                return
        raise KeyError(f"unknown job: {job.get('id')}")

    def remove(self, job_id: str) -> dict[str, Any] | None:
        payload = self.load()
        kept = []
        removed = None
        for job in payload["jobs"]:
            if job.get("id") == job_id:
                removed = job
            else:
                kept.append(job)
        if removed is not None:
            payload["jobs"] = kept
            self.save(payload)
        return removed


class StateStore:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def load(self) -> dict[str, Any]:
        return _read_json(self.paths.state_path, {})

    def save(self, payload: dict[str, Any]) -> None:
        self.paths.ensure()
        _atomic_write_json(self.paths.state_path, payload)

    def record_reset(self, reset_info: dict[str, Any]) -> None:
        payload = self.load()
        payload.update(reset_info)
        payload["updated_at"] = utc_now_iso()
        self.save(payload)

    def record_estimated_reset(
        self, window_started_at: str, next_estimated_reset_at: str
    ) -> None:
        payload = self.load()
        payload["last_estimated_window_started_at"] = window_started_at
        payload["next_estimated_reset_at"] = next_estimated_reset_at
        payload["estimated_reset_source"] = "scheduler-success"
        payload["estimated_reset_confidence"] = "estimated"
        payload["updated_at"] = utc_now_iso()
        self.save(payload)

    def record_rate_limits(self, rate_limits: dict[str, Any]) -> None:
        payload = self.load()
        updated_at = utc_now_iso()
        payload["rate_limits"] = rate_limits
        payload["rate_limits_updated_at"] = updated_at
        payload["updated_at"] = updated_at

        five_hour = rate_limits.get("five_hour")
        if isinstance(five_hour, dict) and five_hour.get("resets_at_iso"):
            payload["next_reset_at"] = five_hour["resets_at_iso"]
            payload["reset_source"] = "claude-code-statusline"

        self.save(payload)
