from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .auth import AUTH_REQUIRED_EXIT_CODE, check_provider_auth, looks_like_auth_required
from .ids import make_job_id
from .launchd import LaunchdManager
from .paths import AppPaths
from .providers import (
    BOTH,
    CLAUDE,
    CODEX,
    expand_provider_selection,
    find_provider_executable,
    normalize_provider,
    normalize_provider_selection,
    provider_label,
    provider_spec,
)
from . import codex_rate_limits
from .reset_parser import looks_like_usage_limit, parse_reset_time
from .schedules import is_due, is_terminal_once_status
from .storage import JobStore, StateStore, utc_now_iso


MINIMAL_WINDOW_PROMPT = "Reply with exactly OK."
PROVIDER_SEND_TIMEOUT_SECONDS = 120
CLAUDE_SEND_TIMEOUT_SECONDS = PROVIDER_SEND_TIMEOUT_SECONDS
ESTIMATED_SESSION_WINDOW = timedelta(hours=5)


@dataclass(frozen=True)
class RunResult:
    status: str
    exit_code: int
    log_path: Path
    reset_info: dict[str, Any] | None = None
    message: str | None = None
    claude_response_summary: str | None = None
    provider: str = CLAUDE
    provider_results: tuple["RunResult", ...] | None = None


class RunnerError(RuntimeError):
    pass


def _timestamp_for_filename(now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    return now.strftime("%Y%m%dT%H%M%S%z")


def _truncate(value: str, limit: int = 10000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]..."


def extract_response_summary(
    stdout: str,
    *,
    provider: str = CLAUDE,
    final_message: str | None = None,
    limit: int = 4000,
) -> str | None:
    if final_message and final_message.strip():
        return _truncate(final_message.strip(), limit=limit)

    text = stdout.strip()
    if not text:
        return None

    normalized = normalize_provider(provider)
    if normalized == CODEX:
        summary = _extract_codex_jsonl_summary(text)
        if summary:
            return _truncate(summary, limit=limit)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _truncate(text, limit=limit)

    if isinstance(payload, dict):
        for key in ("result", "response", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _truncate(value.strip(), limit=limit)

    return _truncate(text, limit=limit)


def extract_claude_response_summary(stdout: str, *, limit: int = 4000) -> str | None:
    return extract_response_summary(stdout, provider=CLAUDE, limit=limit)


def _extract_codex_jsonl_summary(text: str) -> str | None:
    summaries: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        summary = _text_from_nested_payload(payload)
        if summary:
            summaries.append(summary)
    if summaries:
        return summaries[-1]
    return None


def _text_from_nested_payload(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload.strip() or None
    if isinstance(payload, list):
        parts = [_text_from_nested_payload(item) for item in payload]
        text = "\n".join(part for part in parts if part)
        return text or None
    if not isinstance(payload, dict):
        return None

    event_type = str(payload.get("type") or payload.get("event") or "").lower()
    preferred = (
        "final",
        "agent_message",
        "assistant_message",
        "message",
        "response",
    )
    if event_type and not any(marker in event_type for marker in preferred):
        nested = payload.get("payload") or payload.get("data")
        return _text_from_nested_payload(nested)

    for key in ("text", "message", "content", "final_message", "last_message", "response"):
        value = payload.get(key)
        summary = _text_from_nested_payload(value)
        if summary:
            return summary

    nested = payload.get("payload") or payload.get("data") or payload.get("item")
    return _text_from_nested_payload(nested)


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
        handle.write(f"provider: {_job_provider_selection(job)}\n")
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


def _message_from_result(
    status: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    *,
    provider: str = CLAUDE,
) -> str | None:
    label = provider_spec(provider).label
    if status == "success":
        return None
    if status == "timed_out":
        return f"{label} did not finish within the timeout."
    output = (stderr or stdout).strip()
    if output:
        return _truncate(output, limit=500)
    if status == "failed":
        return f"{label} exited with code {exit_code}."
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


def _refresh_codex_rate_limits(paths: AppPaths) -> None:
    rate_limits = codex_rate_limits.latest_rate_limits()
    if rate_limits is None:
        return
    StateStore(paths).record_codex_rate_limits(
        codex_rate_limits.to_state_payload(rate_limits)
    )


def _job_provider_selection(job: dict[str, Any]) -> str:
    return normalize_provider_selection(job.get("provider"), default=CLAUDE)


def _provider_executable(
    provider: str,
    *,
    provider_bin: str | None,
    claude_bin: str | None,
    codex_bin: str | None,
) -> str | None:
    if provider_bin:
        return provider_bin
    if provider == CLAUDE and claude_bin:
        return claude_bin
    if provider == CODEX and codex_bin:
        return codex_bin
    return find_provider_executable(provider)


def _codex_response_path(paths: AppPaths, job_id: str, timestamp: str) -> Path:
    return paths.logs_dir / f"{job_id}-{timestamp}.response.txt"


def _build_prompt_command(
    provider: str,
    executable: str,
    *,
    cwd: Path,
    prompt: str,
    response_path: Path | None,
) -> list[str]:
    if provider == CLAUDE:
        return [
            executable,
            "-p",
            "--max-turns",
            "1",
            "--no-session-persistence",
            "--output-format",
            "json",
            prompt,
        ]
    if provider == CODEX:
        command = [
            executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--cd",
            str(cwd),
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--ephemeral",
            "--color",
            "never",
        ]
        if response_path is not None:
            command.extend(["--output-last-message", str(response_path)])
        command.append(prompt)
        return command
    raise RunnerError(f"unsupported provider: {provider}")


def _read_response_path(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _execute_job(
    job: dict[str, Any],
    *,
    paths: AppPaths,
    provider_bin: str | None = None,
    claude_bin: str | None = None,
    codex_bin: str | None = None,
    now: datetime | None = None,
    persist: bool = True,
    cleanup_launchd: bool = True,
) -> RunResult:
    paths.ensure()
    store = JobStore(paths)
    job_id = job["id"]
    timestamp = _timestamp_for_filename(now)
    log_path = paths.logs_dir / f"{job_id}-{timestamp}.log"
    schedule_type = job.get("schedule", {}).get("type")
    provider = _job_provider_selection(job)
    if provider == BOTH:
        return _execute_multi_provider_job(
            job,
            paths=paths,
            claude_bin=claude_bin,
            codex_bin=codex_bin,
            now=now,
            persist=persist,
            cleanup_launchd=cleanup_launchd,
        )
    spec = provider_spec(provider)

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
                return RunResult(
                    "skipped",
                    0,
                    log_path,
                    message="one-time job already completed",
                    provider=provider,
                )

            if not is_due(job, now):
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status="skipped",
                    exit_code=0,
                    note="one-time job is not due yet",
                )
                return RunResult(
                    "skipped",
                    0,
                    log_path,
                    message="one-time job is not due yet",
                    provider=provider,
                )

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
                    provider=provider,
                )

            executable = _provider_executable(
                provider,
                provider_bin=provider_bin,
                claude_bin=claude_bin,
                codex_bin=codex_bin,
            )
            if not executable:
                status = "failed"
                stderr = f"{spec.executable} executable was not found on PATH"
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
                return RunResult(status, 127, log_path, message=stderr, provider=provider)

            auth = check_provider_auth(provider, executable)
            if auth.authenticated is False:
                status = "auth_required"
                stderr = auth.error or f"{spec.label} login required."
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status=status,
                    exit_code=AUTH_REQUIRED_EXIT_CODE,
                    stderr=stderr,
                    note=f"{spec.label} authentication is required before sending prompts.",
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
                return RunResult(
                    status,
                    AUTH_REQUIRED_EXIT_CODE,
                    log_path,
                    message=stderr,
                    provider=provider,
                )

            response_path = _codex_response_path(paths, job_id, timestamp) if provider == CODEX else None
            command = _build_prompt_command(
                provider,
                executable,
                cwd=cwd,
                prompt=job["prompt"],
                response_path=response_path,
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(cwd),
                    text=True,
                    capture_output=True,
                    timeout=PROVIDER_SEND_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                status = "timed_out"
                stdout = _timeout_output(exc.stdout)
                stderr = _timeout_output(exc.stderr)
                final_message = _read_response_path(response_path)
                response_summary = extract_response_summary(
                    stdout,
                    provider=provider,
                    final_message=final_message,
                )
                message = f"{spec.label} did not finish within the timeout."
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
                return RunResult(
                    status,
                    124,
                    log_path,
                    message=message,
                    claude_response_summary=response_summary,
                    provider=provider,
                )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            combined = f"{stdout}\n{stderr}"
            final_message = _read_response_path(response_path)
            response_summary = extract_response_summary(
                stdout,
                provider=provider,
                final_message=final_message,
            )
            reset_info = parse_reset_time(combined)
            status = _status_from_result(completed.returncode, combined)
            if reset_info:
                StateStore(paths).record_reset(reset_info)
            elif status == "success" and provider == CLAUDE:
                _record_success_estimate(paths, started_at)
            if provider == CODEX:
                _refresh_codex_rate_limits(paths)
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
                provider=provider,
                response_summary=response_summary,
            )
            _cleanup_once(job, paths, cleanup_launchd)
            return RunResult(
                status,
                completed.returncode,
                log_path,
                reset_info,
                _message_from_result(
                    status,
                    completed.returncode,
                    stdout,
                    stderr,
                    provider=provider,
                ),
                response_summary,
                provider,
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
        return RunResult(
            "overlap_skipped",
            2,
            log_path,
            message="job is already running",
            provider=provider,
        )


def _execute_multi_provider_job(
    job: dict[str, Any],
    *,
    paths: AppPaths,
    claude_bin: str | None = None,
    codex_bin: str | None = None,
    now: datetime | None = None,
    persist: bool = True,
    cleanup_launchd: bool = True,
) -> RunResult:
    paths.ensure()
    store = JobStore(paths)
    job_id = job["id"]
    timestamp = _timestamp_for_filename(now)
    log_path = paths.logs_dir / f"{job_id}-{timestamp}.log"
    schedule_type = job.get("schedule", {}).get("type")
    provider = _job_provider_selection(job)

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
                return RunResult(
                    "skipped",
                    0,
                    log_path,
                    message="one-time job already completed",
                    provider=provider,
                )

            if not is_due(job, now):
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status="skipped",
                    exit_code=0,
                    note="one-time job is not due yet",
                )
                return RunResult(
                    "skipped",
                    0,
                    log_path,
                    message="one-time job is not due yet",
                    provider=provider,
                )

            cwd = Path(job["cwd"]).expanduser()
            if not cwd.is_dir():
                status = "failed"
                stderr = f"cwd does not exist or is not a directory: {cwd}"
                _write_log(
                    log_path,
                    job=job,
                    command=None,
                    status=status,
                    exit_code=1,
                    stderr=stderr,
                )
                _update_after_run(store, job, status, 1, log_path, "", stderr, persist)
                _cleanup_once(job, paths, cleanup_launchd)
                return RunResult(status, 1, log_path, message=stderr, provider=provider)

            results: list[RunResult] = []
            for child_provider in expand_provider_selection(provider):
                child_job = dict(job)
                child_job["id"] = f"{job_id}-{child_provider}"
                child_job["provider"] = child_provider
                child_job["_started_at"] = started_at
                results.append(
                    _execute_job(
                        child_job,
                        paths=paths,
                        claude_bin=claude_bin,
                        codex_bin=codex_bin,
                        now=now,
                        persist=False,
                        cleanup_launchd=False,
                    )
                )

            status = _aggregate_status(results)
            exit_code = _aggregate_exit_code(results, status)
            response_summary = _aggregate_response_summary(results)
            stdout = _aggregate_result_text(results)
            stderr = _aggregate_error_text(results)
            reset_info = next(
                (result.reset_info for result in results if result.reset_info),
                None,
            )
            message = _aggregate_message(results, status)

            _write_log(
                log_path,
                job=job,
                command=None,
                status=status,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                note="sent prompt to Codex and Claude Code",
            )
            _update_after_run(
                store,
                job,
                status,
                exit_code,
                log_path,
                stdout,
                stderr,
                persist,
                provider=provider,
                response_summary=response_summary,
            )
            _cleanup_once(job, paths, cleanup_launchd)
            return RunResult(
                status,
                exit_code,
                log_path,
                reset_info,
                message,
                response_summary,
                provider,
                tuple(results),
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
        return RunResult(
            "overlap_skipped",
            2,
            log_path,
            message="job is already running",
            provider=provider,
        )


def _aggregate_status(results: list[RunResult]) -> str:
    statuses = [result.status for result in results]
    if statuses and all(status == "success" for status in statuses):
        return "success"
    if any(status == "success" for status in statuses):
        return "partial_success"
    if len(set(statuses)) == 1:
        return statuses[0]
    for status in (
        "auth_required",
        "usage_limit",
        "timed_out",
        "overlap_skipped",
        "failed",
    ):
        if status in statuses:
            return status
    return statuses[0] if statuses else "failed"


def _aggregate_exit_code(results: list[RunResult], status: str) -> int:
    if status == "success":
        return 0
    for result in results:
        if result.exit_code != 0:
            return result.exit_code
    return 1


def _aggregate_response_summary(results: list[RunResult]) -> str | None:
    lines = []
    for result in results:
        text = result.claude_response_summary or result.message or result.status
        if text:
            lines.append(f"{provider_label(result.provider)}: {text}")
    return "\n".join(lines) if lines else None


def _aggregate_result_text(results: list[RunResult]) -> str:
    lines = []
    for result in results:
        lines.append(
            f"{provider_label(result.provider)}: {result.status} "
            f"(exit {result.exit_code}) log={result.log_path}"
        )
        text = result.claude_response_summary or result.message
        if text:
            lines.append(text)
    return "\n".join(lines)


def _aggregate_error_text(results: list[RunResult]) -> str:
    lines = []
    for result in results:
        if result.status == "success":
            continue
        text = result.message or result.status
        lines.append(f"{provider_label(result.provider)}: {text}")
    return "\n".join(lines)


def _aggregate_message(results: list[RunResult], status: str) -> str | None:
    if status == "success":
        return None
    failures = [
        f"{provider_label(result.provider)}: {result.message or result.status}"
        for result in results
        if result.status != "success"
    ]
    if status == "partial_success":
        return "Some providers failed: " + "; ".join(failures)
    if failures:
        return "All providers failed: " + "; ".join(failures)
    return None


def _update_after_run(
    store: JobStore,
    job: dict[str, Any],
    status: str,
    exit_code: int,
    log_path: Path,
    stdout: str,
    stderr: str,
    persist: bool,
    *,
    provider: str | None = None,
    response_summary: str | None = None,
) -> None:
    provider = normalize_provider_selection(provider or job.get("provider"), default=CLAUDE)
    if response_summary is None:
        response_summary = (
            _truncate(stdout)
            if provider == BOTH
            else extract_response_summary(stdout, provider=provider)
        )
    job.pop("_started_at", None)
    job["provider"] = provider
    job["last_status"] = status
    job["last_run_at"] = utc_now_iso()
    job["last_exit_code"] = exit_code
    job["last_log_path"] = str(log_path)
    job["last_stdout_summary"] = _truncate(stdout)
    job["last_stderr_summary"] = _truncate(stderr)
    job["last_response_summary"] = response_summary
    job["last_claude_response_summary"] = response_summary
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
    provider_bin: str | None = None,
    claude_bin: str | None = None,
    codex_bin: str | None = None,
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
        provider_bin=provider_bin,
        claude_bin=claude_bin,
        codex_bin=codex_bin,
        now=now,
        persist=True,
        cleanup_launchd=cleanup_launchd,
    )


def run_inline_prompt(
    *,
    cwd: str,
    prompt: str = MINIMAL_WINDOW_PROMPT,
    paths: AppPaths | None = None,
    provider: str = CLAUDE,
    provider_bin: str | None = None,
    claude_bin: str | None = None,
    codex_bin: str | None = None,
) -> RunResult:
    provider = normalize_provider_selection(provider, default=CLAUDE)
    paths = paths or AppPaths.from_env()
    job = {
        "id": make_job_id("manual-window-start"),
        "name": "manual-window-start",
        "cwd": cwd,
        "prompt": prompt,
        "provider": provider,
        "schedule": {"type": "manual"},
        "status": "manual",
        "created_at": utc_now_iso(),
        "run_count": 0,
    }
    return _execute_job(
        job,
        paths=paths,
        provider_bin=provider_bin,
        claude_bin=claude_bin,
        codex_bin=codex_bin,
        persist=False,
        cleanup_launchd=False,
    )
