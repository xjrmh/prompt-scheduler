from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .auth import AUTH_REQUIRED_EXIT_CODE, check_claude_auth, looks_like_auth_required
from .ids import make_job_id
from .launchd import LaunchdManager
from .paths import AppPaths
from .reset_parser import looks_like_usage_limit, parse_reset_time
from .schedules import is_due, is_terminal_once_status
from .storage import JobStore, StateStore, utc_now_iso


MINIMAL_WINDOW_PROMPT = "Reply with exactly OK."
CLAUDE_SEND_TIMEOUT_SECONDS = 120
ESTIMATED_SESSION_WINDOW = timedelta(hours=5)


@dataclass(frozen=True)
class RunResult:
    status: str
    exit_code: int
    log_path: Path
    reset_info: dict[str, Any] | None = None
    message: str | None = None


class RunnerError(RuntimeError):
    pass


def _timestamp_for_filename(now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    return now.strftime("%Y%m%dT%H%M%S%z")


def _truncate(value: str, limit: int = 10000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]..."


class JobLock:
    def __init__(self, paths: AppPaths, job_id: str):
        self.path = paths.locks_dir / f"{job_id}.lock"
        self.fd: int | None = None

    def __enter__(self) -> "JobLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError as exc:
            raise RunnerError("job is already running") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


def _write_log(
    log_path: Path,
    *,
    job: dict[str, Any],
    command: list[str] | None,
    status: str,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    note: str = "",
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = job.get("prompt", "")
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"job_id: {job.get('id')}\n")
        handle.write(f"name: {job.get('name')}\n")
        handle.write(f"cwd: {job.get('cwd')}\n")
        handle.write(f"status: {status}\n")
        handle.write(f"exit_code: {exit_code}\n")
        handle.write(f"started_at: {job.get('_started_at', '')}\n")
        handle.write(f"ended_at: {utc_now_iso()}\n")
        if note:
            handle.write(f"note: {note}\n")
        if command:
            display_command = command[:-1] + ["<prompt>"]
            handle.write(f"command: {display_command!r}\n")
        handle.write("\n[prompt]\n")
        handle.write(prompt)
        handle.write("\n\n[stdout]\n")
        handle.write(stdout)
        handle.write("\n\n[stderr]\n")
        handle.write(stderr)
        handle.write("\n")


def _status_from_result(exit_code: int, combined_output: str) -> str:
    if looks_like_auth_required(combined_output):
        return "auth_required"
    if looks_like_usage_limit(combined_output):
        return "usage_limit"
    if exit_code == 0:
        return "success"
    return "failed"


def _message_from_result(status: str, exit_code: int, stdout: str, stderr: str) -> str | None:
    if status == "success":
        return None
    if status == "timed_out":
        return "Claude did not finish within the timeout."
    output = (stderr or stdout).strip()
    if output:
        return _truncate(output, limit=500)
    if status == "failed":
        return f"Claude exited with code {exit_code}."
    return None


def _timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _parse_state_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _record_success_estimate(paths: AppPaths, started_at: str) -> None:
    started = datetime.fromisoformat(started_at)
    store = StateStore(paths)
    state = store.load()
    current_estimate = _parse_state_datetime(state.get("next_estimated_reset_at"))
    if current_estimate is not None and current_estimate > started:
        return
    store.record_estimated_reset(
        started.isoformat(), (started + ESTIMATED_SESSION_WINDOW).isoformat()
    )


def _execute_job(
    job: dict[str, Any],
    *,
    paths: AppPaths,
    claude_bin: str | None = None,
    now: datetime | None = None,
    persist: bool = True,
    cleanup_launchd: bool = True,
) -> RunResult:
    paths.ensure()
    store = JobStore(paths)
    job_id = job["id"]
    log_path = paths.logs_dir / f"{job_id}-{_timestamp_for_filename(now)}.log"
    schedule_type = job.get("schedule", {}).get("type")

    try:
        with JobLock(paths, job_id):
            started_at = utc_now_iso()
            job["_started_at"] = started_at

            if schedule_type == "once" and is_terminal_once_status(job.get("status")):
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status="skipped",
                    exit_code=0,
                    note="one-time job already completed",
                )
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult("skipped", 0, log_path, message="one-time job already completed")

            if not is_due(job, now):
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status="skipped",
                    exit_code=0,
                    note="one-time job is not due yet",
                )
                return RunResult("skipped", 0, log_path, message="one-time job is not due yet")

            cwd = Path(job["cwd"]).expanduser()
            if not cwd.is_dir():
                status = "failed"
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status=status,
                    exit_code=1,
                    stderr=f"cwd does not exist or is not a directory: {cwd}",
                )
                _update_after_run(
                    store, job, status, 1, log_path, "", str(cwd), persist
                )
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult(
                    status,
                    1,
                    log_path,
                    message=f"cwd does not exist or is not a directory: {cwd}",
                )

            claude = claude_bin or shutil.which("claude")
            if not claude:
                status = "failed"
                stderr = "claude executable was not found on PATH"
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status=status,
                    exit_code=127,
                    stderr=stderr,
                )
                _update_after_run(store, job, status, 127, log_path, "", stderr, persist)
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult(status, 127, log_path, message=stderr)

            auth = check_claude_auth(claude)
            if auth.authenticated is False:
                status = "auth_required"
                stderr = auth.error or "Claude login required. Run `claude auth login`."
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status=status,
                    exit_code=AUTH_REQUIRED_EXIT_CODE,
                    stderr=stderr,
                    note="Claude authentication is required before sending prompts.",
                )
                _update_after_run(
                    store,
                    job,
                    status,
                    AUTH_REQUIRED_EXIT_CODE,
                    log_path,
                    "",
                    stderr,
                    persist,
                )
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult(status, AUTH_REQUIRED_EXIT_CODE, log_path, message=stderr)

            command = [
                claude,
                "-p",
                "--max-turns",
                "1",
                "--no-session-persistence",
                "--output-format",
                "json",
                job["prompt"],
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(cwd),
                    text=True,
                    capture_output=True,
                    timeout=CLAUDE_SEND_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                status = "timed_out"
                stdout = _timeout_output(exc.stdout)
                stderr = _timeout_output(exc.stderr)
                message = "Claude did not finish within the timeout."
                stderr = f"{stderr}\n{message}".strip()
                _write_log(
                    log_path,
                    job=job,
                    command=command,
                    status=status,
                    exit_code=124,
                    stdout=stdout,
                    stderr=stderr,
                )
                _update_after_run(store, job, status, 124, log_path, stdout, stderr, persist)
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult(status, 124, log_path, message=message)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            combined = f"{stdout}\n{stderr}"
            reset_info = parse_reset_time(combined)
            status = _status_from_result(completed.returncode, combined)
            if reset_info:
                StateStore(paths).record_reset(reset_info)
            elif status == "success":
                _record_success_estimate(paths, started_at)
            _write_log(
                log_path,
                job=job,
                command=command,
                status=status,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            _update_after_run(
                store,
                job,
                status,
                completed.returncode,
                log_path,
                stdout,
                stderr,
                persist,
            )
            _cleanup_once(job, paths, cleanup_launchd)
            return RunResult(
                status,
                completed.returncode,
                log_path,
                reset_info,
                _message_from_result(status, completed.returncode, stdout, stderr),
            )
    except RunnerError:
        _write_log(
            log_path,
            job=job,
            command=None,
            status="overlap_skipped",
            exit_code=2,
            note="job is already running",
        )
        return RunResult("overlap_skipped", 2, log_path, message="job is already running")


def _update_after_run(
    store: JobStore,
    job: dict[str, Any],
    status: str,
    exit_code: int,
    log_path: Path,
    stdout: str,
    stderr: str,
    persist: bool,
) -> None:
    job.pop("_started_at", None)
    job["last_status"] = status
    job["last_run_at"] = utc_now_iso()
    job["last_exit_code"] = exit_code
    job["last_log_path"] = str(log_path)
    job["last_stdout_summary"] = _truncate(stdout)
    job["last_stderr_summary"] = _truncate(stderr)
    job["run_count"] = int(job.get("run_count", 0)) + 1
    if job.get("schedule", {}).get("type") == "once":
        job["status"] = "completed" if status == "success" else status
        job["completed_at"] = utc_now_iso()
    if persist:
        store.update(job)


def _cleanup_once(job: dict[str, Any], paths: AppPaths, cleanup_launchd: bool) -> None:
    if cleanup_launchd and job.get("schedule", {}).get("type") == "once":
        LaunchdManager(paths).uninstall(job, ignore_errors=True)


def run_job(
    job_id: str,
    *,
    paths: AppPaths | None = None,
    claude_bin: str | None = None,
    now: datetime | None = None,
    cleanup_launchd: bool = True,
) -> RunResult:
    paths = paths or AppPaths.from_env()
    job = JobStore(paths).get(job_id)
    if job is None:
        raise RunnerError(f"unknown job: {job_id}")
    return _execute_job(
        job,
        paths=paths,
        claude_bin=claude_bin,
        now=now,
        persist=True,
        cleanup_launchd=cleanup_launchd,
    )


def run_inline_prompt(
    *,
    cwd: str,
    prompt: str = MINIMAL_WINDOW_PROMPT,
    paths: AppPaths | None = None,
    claude_bin: str | None = None,
) -> RunResult:
    paths = paths or AppPaths.from_env()
    job = {
        "id": make_job_id("manual-window-start"),
        "name": "manual-window-start",
        "cwd": cwd,
        "prompt": prompt,
        "schedule": {"type": "manual"},
        "status": "manual",
        "created_at": utc_now_iso(),
        "run_count": 0,
    }
    return _execute_job(
        job,
        paths=paths,
        claude_bin=claude_bin,
        persist=False,
        cleanup_launchd=False,
    )
