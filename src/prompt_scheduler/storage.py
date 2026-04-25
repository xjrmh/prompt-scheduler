from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .paths import AppPaths


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat()


@contextlib.contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        # Quarantine the corrupt file so the user can recover it manually,
        # then continue with defaults instead of crashing every command.
        backup = path.with_suffix(path.suffix + ".corrupt")
        with contextlib.suppress(OSError):
            os.replace(path, backup)
        return default


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


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
        self.paths.ensure()
        with _file_lock(self.paths.jobs_path):
            payload = self.load()
            payload["jobs"].append(job)
            self.save(payload)

    def update(self, job: dict[str, Any]) -> None:
        self.paths.ensure()
        with _file_lock(self.paths.jobs_path):
            payload = self.load()
            for index, existing in enumerate(payload["jobs"]):
                if existing.get("id") == job.get("id"):
                    job["updated_at"] = utc_now_iso()
                    payload["jobs"][index] = job
                    self.save(payload)
                    return
            raise KeyError(f"unknown job: {job.get('id')}")

    def remove(self, job_id: str) -> dict[str, Any] | None:
        self.paths.ensure()
        with _file_lock(self.paths.jobs_path):
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
        self.paths.ensure()
        with _file_lock(self.paths.state_path):
            payload = self.load()
            payload.update(reset_info)
            payload["updated_at"] = utc_now_iso()
            self.save(payload)

    def record_estimated_reset(
        self, window_started_at: str, next_estimated_reset_at: str
    ) -> None:
        self.paths.ensure()
        with _file_lock(self.paths.state_path):
            payload = self.load()
            payload["last_estimated_window_started_at"] = window_started_at
            payload["next_estimated_reset_at"] = next_estimated_reset_at
            payload["estimated_reset_source"] = "scheduler-success"
            payload["estimated_reset_confidence"] = "estimated"
            payload["updated_at"] = utc_now_iso()
            self.save(payload)

    def record_rate_limits(self, rate_limits: dict[str, Any]) -> None:
        self.paths.ensure()
        with _file_lock(self.paths.state_path):
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

    def record_codex_rate_limits(self, fields: dict[str, Any]) -> None:
        self.paths.ensure()
        with _file_lock(self.paths.state_path):
            payload = self.load()
            updated_at = utc_now_iso()
            payload.update(fields)
            payload["codex_rate_limits_updated_at"] = updated_at
            payload["updated_at"] = updated_at
            self.save(payload)
