from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .auth import ClaudeAuthCheck, check_claude_auth
from .ids import make_job_id
from .installer import (
    CLAUDE_INSTALL_COMMAND,
    ClaudeInstallError,
    install_claude_code,
    validate_claude_install_prerequisites,
)
from .launchd import LaunchdError, LaunchdManager
from .paths import AppPaths
from .runner import (
    MINIMAL_WINDOW_PROMPT,
    RunnerError,
    extract_claude_response_summary,
    run_inline_prompt,
    run_job,
)
from .schedules import ScheduleError, format_schedule, parse_once, parse_schedule
from .storage import JobStore, StateStore, utc_now_iso


DEFAULT_PROJECT_FOLDER_NAME = "Claude Scheduler Project"
STATUSLINE_COMMAND = "python3 -m claude_session_scheduler statusline"
RATE_LIMIT_WINDOWS = ("five_hour", "seven_day")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-session-scheduler",
        description="Schedule local Claude Code prompts with macOS launchd.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Set up Claude Session Scheduler.")
    _add_install_flags(setup)
    _add_json_flag(setup)

    doctor = subparsers.add_parser("doctor", help="Check local prerequisites.")
    _add_install_flags(doctor)
    _add_json_flag(doctor)

    top_add = subparsers.add_parser("add", help="Add a scheduled Claude prompt.")
    _add_schedule_args(top_add, required=False)
    _add_json_flag(top_add)

    top_list = subparsers.add_parser("list", help="List scheduled jobs.")
    _add_json_flag(top_list)
    top_remove = subparsers.add_parser("remove", help="Remove a scheduled job.")
    top_remove.add_argument("job_id")
    _add_json_flag(top_remove)

    status = subparsers.add_parser("status", help="Show setup, reset, and job status.")
    _add_json_flag(status)

    statusline = subparsers.add_parser(
        "statusline",
        help="Capture Claude Code status-line usage data and print a compact status line.",
    )

    install_statusline = subparsers.add_parser(
        "install-statusline",
        help="Configure Claude Code to report usage limits to this app.",
    )
    install_statusline.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing Claude Code statusLine command.",
    )
    install_statusline.add_argument(
        "--settings",
        help="Path to Claude Code settings.json. Defaults to ~/.claude/settings.json.",
    )
    _add_json_flag(install_statusline)

    start_now = subparsers.add_parser(
        "start-now", help="Start a Claude session by sending a tiny OK prompt."
    )
    start_now.add_argument("--cwd", default=None)
    _add_json_flag(start_now)

    start_reset = subparsers.add_parser(
        "start-at-reset", help="Schedule the minimal prompt at the observed reset time."
    )
    start_reset.add_argument("--cwd", default=None)
    start_reset.add_argument("--buffer-minutes", type=int, default=2)
    start_reset.add_argument("--dry-run", action="store_true")
    _add_json_flag(start_reset)

    schedule = subparsers.add_parser("schedule", help="Manage scheduled jobs.")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    add = schedule_sub.add_parser("add", help="Add a scheduled Claude prompt.")
    _add_schedule_args(add, required=True)
    _add_json_flag(add)

    nested_list = schedule_sub.add_parser("list", help="List jobs.")
    _add_json_flag(nested_list)
    remove = schedule_sub.add_parser("remove", help="Remove a scheduled job.")
    remove.add_argument("job_id")
    _add_json_flag(remove)

    run = subparsers.add_parser("run", help="Run a job by id.")
    run.add_argument("job_id")

    window = subparsers.add_parser("window", help="Start Claude usage windows.")
    window_sub = window.add_subparsers(dest="window_command", required=True)
    start_now = window_sub.add_parser(
        "start-now", help="Start a Claude session by sending a tiny OK prompt."
    )
    start_now.add_argument("--cwd", required=True)
    _add_json_flag(start_now)
    start_reset = window_sub.add_parser(
        "start-at-reset", help="Schedule the minimal prompt at the observed reset time."
    )
    start_reset.add_argument("--cwd", required=True)
    start_reset.add_argument("--buffer-minutes", type=int, default=2)
    start_reset.add_argument("--dry-run", action="store_true")
    _add_json_flag(start_reset)

    logs = subparsers.add_parser("logs", help="Show recent logs or one job's latest log.")
    logs.add_argument("job_id", nargs="?")
    _add_json_flag(logs)

    return parser


def _add_install_flags(parser: argparse.ArgumentParser) -> None:
    install = parser.add_mutually_exclusive_group()
    install.add_argument(
        "--yes",
        action="store_true",
        help="Install Claude Code without prompting if it is missing.",
    )
    install.add_argument(
        "--no-install",
        action="store_true",
        help="Only report missing Claude Code; do not prompt to install it.",
    )


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON response.",
    )


def _add_schedule_args(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--name", required=required)
    parser.add_argument("--cwd", required=required)
    parser.add_argument("--prompt", required=required)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated job and plist without writing or loading them.",
    )
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--at", help='One-time local datetime, "YYYY-MM-DD HH:MM".')
    group.add_argument("--daily", help='Daily local time, "HH:MM".')
    group.add_argument("--weekly", help='Weekly schedule, e.g. "Mon-Fri 09:00".')


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = AppPaths.from_env()
    try:
        if args.command == "setup":
            return command_setup(
                paths,
                assume_yes=args.yes,
                prompt_install=not args.no_install,
                json_output=args.json,
            )
        if args.command == "doctor":
            return command_doctor(
                paths,
                assume_yes=args.yes,
                prompt_install=not args.no_install,
                json_output=args.json,
            )
        if args.command == "add":
            return schedule_add(args, paths, interactive=True)
        if args.command == "list":
            return schedule_list(paths, json_output=args.json)
        if args.command == "remove":
            return schedule_remove(args.job_id, paths, json_output=args.json)
        if args.command == "status":
            return command_status(paths, json_output=args.json)
        if args.command == "statusline":
            return command_statusline(paths)
        if args.command == "install-statusline":
            return command_install_statusline(args, paths)
        if args.command == "start-now":
            return command_start_now(args.cwd or str(Path.cwd()), paths, json_output=args.json)
        if args.command == "start-at-reset":
            if args.cwd is None:
                args.cwd = str(Path.cwd())
            return window_start_at_reset(args, paths)
        if args.command == "schedule":
            return command_schedule(args, paths)
        if args.command == "run":
            return command_run(args, paths)
        if args.command == "window":
            return command_window(args, paths)
        if args.command == "logs":
            return command_logs(args, paths)
    except (
        ClaudeInstallError,
        ScheduleError,
        LaunchdError,
        RunnerError,
        ValueError,
        OSError,
    ) as exc:
        if _args_wants_json(args):
            _emit_json({"ok": False, "error": str(exc)})
            return 1
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


def _args_wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def command_statusline(paths: AppPaths) -> int:
    raw_input = sys.stdin.read()
    try:
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    rate_limits = _normalize_rate_limits(payload)
    if rate_limits:
        StateStore(paths).record_rate_limits(rate_limits)

    print(_statusline_text(payload, rate_limits))
    return 0


def command_install_statusline(args: argparse.Namespace, paths: AppPaths) -> int:
    settings_path = Path(args.settings).expanduser() if args.settings else _claude_settings_path()
    settings = _load_claude_settings(settings_path)
    existing = settings.get("statusLine")
    already_installed = _is_scheduler_statusline(existing)
    replaced = bool(existing and not already_installed)

    if replaced and not args.force:
        raise ValueError(
            "Claude Code statusLine is already configured; rerun with "
            "`claude-session-scheduler install-statusline --force` to replace it."
        )

    settings["statusLine"] = {"type": "command", "command": STATUSLINE_COMMAND}
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, sort_keys=True)
        handle.write("\n")

    result = {
        "ok": True,
        "settings": str(settings_path),
        "command": STATUSLINE_COMMAND,
        "replaced": replaced,
        "already_installed": already_installed,
    }
    if args.json:
        _emit_json(result)
        return 0

    if already_installed:
        print(f"Claude Code status line already reports to {STATUSLINE_COMMAND}.")
    elif replaced:
        print("Replaced existing Claude Code statusLine command.")
    else:
        print("Installed Claude Code status-line usage bridge.")
    print(f"settings: {settings_path}")
    print(f"command: {STATUSLINE_COMMAND}")
    return 0


def _claude_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _load_claude_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    with settings_path.open("r", encoding="utf-8") as handle:
        settings = json.load(handle)
    if not isinstance(settings, dict):
        raise ValueError(f"Claude Code settings must be a JSON object: {settings_path}")
    return settings


def _is_scheduler_statusline(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "command"
        and value.get("command") == STATUSLINE_COMMAND
    )


def _normalize_rate_limits(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_rate_limits = payload.get("rate_limits")
    if not isinstance(raw_rate_limits, dict):
        return {}

    normalized: dict[str, Any] = {}
    for window_name in RATE_LIMIT_WINDOWS:
        raw_window = raw_rate_limits.get(window_name)
        if not isinstance(raw_window, dict):
            continue

        window: dict[str, Any] = {}
        used_percentage = _coerce_float(raw_window.get("used_percentage"))
        if used_percentage is not None:
            window["used_percentage"] = max(0.0, min(100.0, used_percentage))

        resets_at_iso = _coerce_reset_iso(raw_window.get("resets_at"))
        if resets_at_iso is not None:
            window["resets_at"] = raw_window.get("resets_at")
            window["resets_at_iso"] = resets_at_iso

        if window:
            normalized[window_name] = window

    return normalized


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_reset_iso(value: Any) -> str | None:
    numeric = _coerce_float(value)
    if numeric is not None and numeric > 0:
        return datetime.fromtimestamp(numeric).astimezone().isoformat()

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone().isoformat()
    except ValueError:
        return None


def _statusline_text(payload: Any, rate_limits: dict[str, Any]) -> str:
    model = "Claude"
    if isinstance(payload, dict):
        raw_model = payload.get("model")
        if isinstance(raw_model, dict):
            model = raw_model.get("display_name") or raw_model.get("id") or model

    parts = [f"[{model}]"]
    five_hour = rate_limits.get("five_hour")
    if isinstance(five_hour, dict):
        parts.append(_format_limit_status("5h", five_hour))

    seven_day = rate_limits.get("seven_day")
    if isinstance(seven_day, dict):
        parts.append(_format_limit_status("7d", seven_day))

    return " | ".join(part for part in parts if part)


def _format_limit_status(label: str, window: dict[str, Any]) -> str:
    parts = [label]
    used_percentage = window.get("used_percentage")
    if isinstance(used_percentage, (int, float)):
        parts.append(f"{used_percentage:.0f}%")

    reset_time = _short_time(window.get("resets_at_iso"))
    if reset_time:
        parts.append(f"fresh {reset_time}")

    return " ".join(parts)


def _short_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M")
    except ValueError:
        return None


def command_doctor(
    paths: AppPaths,
    *,
    assume_yes: bool = False,
    prompt_install: bool = True,
    json_output: bool = False,
) -> int:
    paths.ensure()
    claude = shutil.which("claude")
    launchctl = shutil.which("launchctl")
    if json_output:
        if claude is None and prompt_install and assume_yes:
            _maybe_install_claude_json()
            claude = shutil.which("claude")
        payload = _status_payload(paths, claude=claude, launchctl=launchctl)
        ok = _status_checks_ok(payload)
        payload["ok"] = ok
        if claude is None:
            payload["next_commands"] = ["claude-session-scheduler doctor --yes"]
        elif payload["claude"].get("authenticated") is not True:
            payload["next_commands"] = ["claude auth login"]
        _emit_json(payload)
        return 0 if ok else 1

    ok = _print_doctor_checks(paths, claude=claude, launchctl=launchctl)

    if claude is None and prompt_install:
        installed = _maybe_install_claude(
            assume_yes=assume_yes,
            noninteractive_command="claude-session-scheduler doctor --yes",
        )
        if installed:
            claude = shutil.which("claude")
            launchctl = shutil.which("launchctl")
            print()
            ok = _print_doctor_checks(paths, claude=claude, launchctl=launchctl)

    return 0 if ok else 1


def command_setup(
    paths: AppPaths,
    *,
    assume_yes: bool = False,
    prompt_install: bool = True,
    json_output: bool = False,
) -> int:
    if json_output:
        return command_setup_json(
            paths, assume_yes=assume_yes, prompt_install=prompt_install
        )

    print("Claude Session Scheduler setup")
    print()
    paths.ensure()
    claude = shutil.which("claude")
    launchctl = shutil.which("launchctl")
    ok = _print_doctor_checks(paths, claude=claude, launchctl=launchctl)

    if claude is None and prompt_install:
        installed = _maybe_install_claude(
            assume_yes=assume_yes,
            noninteractive_command="claude-session-scheduler setup --yes",
        )
        if installed:
            claude = shutil.which("claude")
            launchctl = shutil.which("launchctl")
            print()
            ok = _print_doctor_checks(paths, claude=claude, launchctl=launchctl)

    jobs = JobStore(paths).list_jobs()
    if not sys.stdin.isatty():
        print()
        print("Next commands:")
        if not ok:
            print("  claude-session-scheduler setup --yes")
        print("  claude-session-scheduler add")
        print("  claude-session-scheduler status")
        return 0 if ok else 1

    if ok and not jobs:
        print()
        answer = input("Create your first schedule now? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            args = argparse.Namespace(
                name=None,
                cwd=None,
                prompt=None,
                at=None,
                daily=None,
                weekly=None,
                dry_run=False,
            )
            return schedule_add(args, paths, interactive=True)
        print("Create one later with: claude-session-scheduler add")
    elif ok:
        print()
        print(f"Setup complete. {len(jobs)} job(s) configured.")
        print("Run `claude-session-scheduler status` for an overview.")
    else:
        print()
        print("Fix the missing checks above, then run `claude-session-scheduler setup` again.")

    return 0 if ok else 1


def command_setup_json(
    paths: AppPaths, *, assume_yes: bool = False, prompt_install: bool = True
) -> int:
    paths.ensure()
    claude = shutil.which("claude")
    launchctl = shutil.which("launchctl")
    if claude is None and prompt_install and assume_yes:
        installed = _maybe_install_claude_json()
        if not installed:
            payload = _status_payload(paths, claude=shutil.which("claude"), launchctl=launchctl)
            payload["ok"] = False
            payload["error"] = "Claude Code install failed"
            _emit_json(payload)
            return 1
        claude = shutil.which("claude")
    payload = _status_payload(paths, claude=claude, launchctl=launchctl)
    ok = _status_checks_ok(payload)
    payload["ok"] = ok
    if claude is None:
        payload["next_commands"] = ["claude-session-scheduler setup --yes"]
    elif payload["claude"].get("authenticated") is not True:
        payload["next_commands"] = ["claude auth login"]
    elif not payload["jobs"]:
        payload["next_commands"] = ["claude-session-scheduler add"]
    _emit_json(payload)
    return 0 if ok else 1


def _print_doctor_checks(
    paths: AppPaths, *, claude: str | None, launchctl: str | None
) -> bool:
    auth = check_claude_auth(claude)
    checks = []
    checks.append(("platform macOS", sys.platform == "darwin", sys.platform))
    checks.append(("claude executable", claude is not None, claude or "missing"))
    checks.append(("Claude login", auth.authenticated is True, _auth_check_detail(auth)))
    checks.append(("launchctl", launchctl is not None, launchctl or "missing"))
    checks.append(("data dir", paths.data_dir.exists(), str(paths.data_dir)))
    launch_agents_ok = paths.launch_agents_dir.exists() or paths.launch_agents_dir.parent.exists()
    checks.append(("LaunchAgents dir", launch_agents_ok, str(paths.launch_agents_dir)))

    ok = True
    for label, passed, detail in checks:
        ok = ok and passed
        status = "OK" if passed else "MISSING"
        print(f"{status:7} {label}: {detail}")
    return ok


def _auth_check_detail(auth: ClaudeAuthCheck) -> str:
    if auth.authenticated is True:
        if auth.auth_method:
            return f"signed in via {auth.auth_method}"
        return "signed in"
    if auth.authenticated is False:
        return auth.error or "sign in required"
    return auth.error or "unknown"


def _maybe_install_claude(*, assume_yes: bool, noninteractive_command: str) -> bool:
    command_text = " ".join(CLAUDE_INSTALL_COMMAND)
    print()
    print("Claude Code is required to run scheduled prompts.")
    print(f"Official npm install command: {command_text}")

    try:
        validate_claude_install_prerequisites()
    except ClaudeInstallError as exc:
        print(f"Cannot install automatically: {exc}", file=sys.stderr)
        print(f"Install manually with: {command_text}", file=sys.stderr)
        return False

    if not assume_yes:
        if not sys.stdin.isatty():
            print(
                f"Run `{noninteractive_command}` to install Claude Code.",
                file=sys.stderr,
            )
            return False
        answer = input("Install Claude Code now? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Claude Code install skipped.")
            return False

    print("Installing Claude Code...")
    install_claude_code()
    print("Claude Code install command finished.")
    return True


def _maybe_install_claude_json() -> bool:
    try:
        validate_claude_install_prerequisites()
        install_claude_code(quiet=True)
    except ClaudeInstallError:
        return False
    return True


def _status_checks_ok(payload: dict[str, Any]) -> bool:
    checks = payload["checks"]
    return bool(
        checks["platform_macos"]
        and payload["claude"]["available"]
        and payload["claude"].get("authenticated") is True
        and checks["launchctl"]
        and checks["data_dir"]
        and checks["launch_agents_dir"]
    )


def _status_payload(
    paths: AppPaths,
    *,
    claude: str | None = None,
    launchctl: str | None = None,
) -> dict[str, Any]:
    paths.ensure()
    if claude is None:
        claude = shutil.which("claude")
    if launchctl is None:
        launchctl = shutil.which("launchctl")
    auth = check_claude_auth(claude)
    jobs = [_job_payload(job) for job in JobStore(paths).list_jobs()]
    state = StateStore(paths).load()
    launch_agents_ok = paths.launch_agents_dir.exists() or paths.launch_agents_dir.parent.exists()
    return {
        "ok": bool(
            sys.platform == "darwin"
            and claude
            and auth.authenticated is True
            and launchctl
            and launch_agents_ok
        ),
        "claude": {
            "available": claude is not None,
            "path": claude,
            "authenticated": auth.authenticated,
            "auth_method": auth.auth_method,
            "auth_error": auth.error,
        },
        "reset": {
            "next_reset_at": state.get("next_reset_at"),
            "next_estimated_reset_at": state.get("next_estimated_reset_at"),
            "last_estimated_window_started_at": state.get(
                "last_estimated_window_started_at"
            ),
            "rate_limits": state.get("rate_limits"),
            "rate_limits_updated_at": state.get("rate_limits_updated_at"),
            "reset_source": state.get("reset_source"),
        },
        "jobs": jobs,
        "paths": {
            "state": str(paths.data_dir),
            "logs": str(paths.logs_dir),
            "launch_agents": str(paths.launch_agents_dir),
        },
        "checks": {
            "platform_macos": sys.platform == "darwin",
            "launchctl": launchctl is not None,
            "data_dir": paths.data_dir.exists(),
            "launch_agents_dir": launch_agents_ok,
        },
    }


def _job_payload(job: dict[str, Any]) -> dict[str, Any]:
    schedule = job.get("schedule", {})
    response_summary = job.get("last_claude_response_summary")
    if not response_summary:
        response_summary = extract_claude_response_summary(
            job.get("last_stdout_summary") or ""
        )
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "cwd": job.get("cwd"),
        "schedule": schedule,
        "schedule_label": format_schedule(schedule),
        "status": job.get("status"),
        "last_status": job.get("last_status"),
        "last_run_at": job.get("last_run_at"),
        "last_log_path": job.get("last_log_path"),
        "last_claude_response_summary": response_summary,
        "run_count": job.get("run_count", 0),
    }


def command_schedule(args: argparse.Namespace, paths: AppPaths) -> int:
    if args.schedule_command == "add":
        return schedule_add(args, paths, interactive=False)
    if args.schedule_command == "list":
        return schedule_list(paths, json_output=args.json)
    if args.schedule_command == "remove":
        return schedule_remove(args.job_id, paths, json_output=args.json)
    raise ValueError(f"unknown schedule command: {args.schedule_command}")


def _build_job(name: str, cwd: str, prompt: str, schedule: dict[str, Any]) -> dict[str, Any]:
    cwd_path = Path(cwd).expanduser()
    if not cwd_path.is_dir():
        raise ValueError(f"cwd does not exist or is not a directory: {cwd_path}")
    return {
        "id": make_job_id(name),
        "name": name,
        "cwd": str(cwd_path.resolve()),
        "prompt": prompt,
        "schedule": schedule,
        "status": "scheduled",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "run_count": 0,
    }


def schedule_add(
    args: argparse.Namespace, paths: AppPaths, *, interactive: bool = False
) -> int:
    name, cwd, prompt, schedule = _resolve_add_inputs(args, interactive=interactive)
    job = _build_job(name, cwd, prompt, schedule)
    manager = LaunchdManager(paths)
    result = manager.install(job, dry_run=args.dry_run)
    payload = {
        "ok": True,
        "job": _job_payload(job),
        "launchd": {
            "label": result.label,
            "path": str(result.plist_path),
            "plist": result.plist,
            "loaded": result.loaded,
        },
    }
    if args.dry_run:
        if _args_wants_json(args):
            _emit_json(payload)
            return 0
        print(
            json.dumps(
                {"job": job, "launchd": {"path": str(result.plist_path), "plist": result.plist}},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    JobStore(paths).add(job)
    if _args_wants_json(args):
        _emit_json(payload)
        return 0
    print(f"added {job['id']}")
    print(f"launchd label: {result.label}")
    print(f"plist: {result.plist_path}")
    return 0


def _resolve_add_inputs(
    args: argparse.Namespace, *, interactive: bool
) -> tuple[str, str, str, dict[str, Any]]:
    cwd = args.cwd or str(_ensure_default_project_folder())
    name = args.name
    prompt = args.prompt
    at = args.at
    daily = args.daily
    weekly = args.weekly

    schedule_supplied = any(value is not None for value in (at, daily, weekly))
    missing = []
    if not name:
        missing.append("--name")
    if not prompt:
        missing.append("--prompt")
    if not schedule_supplied:
        missing.append("--at, --daily, or --weekly")

    if missing:
        if not interactive or not sys.stdin.isatty():
            raise ValueError(
                "missing required input: "
                + ", ".join(missing)
                + ". Run `claude-session-scheduler add` in an interactive terminal "
                "or provide flags such as `claude-session-scheduler add --name "
                '"morning" --daily "09:00" --prompt "..."`.'
            )
        print("Create a Claude schedule")
        print()
        cwd = _prompt_with_default("Project folder", cwd)
        if not name:
            name = _prompt_required("Schedule name")
        if not schedule_supplied:
            at, daily, weekly = _prompt_for_schedule()
        if not prompt:
            prompt = _prompt_required("Claude prompt")

    schedule = parse_schedule(at=at, daily=daily, weekly=weekly)
    return name, cwd, prompt, schedule


def _ensure_default_project_folder() -> Path:
    path = Path.home() / DEFAULT_PROJECT_FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prompt_with_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.")


def _prompt_for_schedule() -> tuple[str | None, str | None, str | None]:
    while True:
        kind = input("Schedule type [daily/weekly/once]: ").strip().lower()
        if kind in {"d", "daily", ""}:
            value = _prompt_required("Daily time (HH:MM)")
            try:
                parse_schedule(daily=value)
            except ScheduleError as exc:
                print(f"Invalid daily schedule: {exc}")
                continue
            return None, value, None
        if kind in {"w", "weekly"}:
            value = _prompt_required('Weekly schedule (for example "Mon-Fri 09:00")')
            try:
                parse_schedule(weekly=value)
            except ScheduleError as exc:
                print(f"Invalid weekly schedule: {exc}")
                continue
            return None, None, value
        if kind in {"o", "once", "one-time", "onetime"}:
            value = _prompt_required('One-time run (YYYY-MM-DD HH:MM)')
            try:
                parse_schedule(at=value)
            except ScheduleError as exc:
                print(f"Invalid one-time schedule: {exc}")
                continue
            return value, None, None
        print("Choose daily, weekly, or once.")


def schedule_list(paths: AppPaths, *, json_output: bool = False) -> int:
    jobs = JobStore(paths).list_jobs()
    if json_output:
        _emit_json({"ok": True, "jobs": [_job_payload(job) for job in jobs]})
        return 0
    if not jobs:
        print("No jobs.")
        return 0
    for job in jobs:
        last = job.get("last_status", "never")
        print(
            f"{job['id']}\t{job.get('status', '')}\t{last}\t"
            f"{job.get('name', '')}\t{format_schedule(job.get('schedule', {}))}\t"
            f"{job.get('cwd', '')}"
        )
    return 0


def schedule_remove(job_id: str, paths: AppPaths, *, json_output: bool = False) -> int:
    store = JobStore(paths)
    job = store.get(job_id)
    if job is None:
        raise ValueError(f"unknown job: {job_id}")
    LaunchdManager(paths).uninstall(job, ignore_errors=True)
    store.remove(job_id)
    if json_output:
        _emit_json({"ok": True, "removed": _job_payload(job)})
        return 0
    print(f"removed {job_id}")
    return 0


def command_run(args: argparse.Namespace, paths: AppPaths) -> int:
    result = run_job(args.job_id, paths=paths)
    print(f"{result.status}: {result.log_path}")
    if result.reset_info:
        print(f"observed reset: {result.reset_info['next_reset_at']}")
    return result.exit_code


def command_window(args: argparse.Namespace, paths: AppPaths) -> int:
    if args.window_command == "start-now":
        return command_start_now(args.cwd, paths, json_output=args.json)
    if args.window_command == "start-at-reset":
        return window_start_at_reset(args, paths)
    raise ValueError(f"unknown window command: {args.window_command}")


def command_start_now(cwd: str, paths: AppPaths, *, json_output: bool = False) -> int:
    result = run_inline_prompt(cwd=cwd, paths=paths)
    if json_output:
        _emit_json(_run_result_payload(result))
        return result.exit_code
    print(f"{result.status}: {result.log_path}")
    if result.message:
        print(result.message)
    if result.reset_info:
        print(f"observed reset: {result.reset_info['next_reset_at']}")
    return result.exit_code


def command_status(paths: AppPaths, *, json_output: bool = False) -> int:
    paths.ensure()
    claude = shutil.which("claude")
    payload = _status_payload(paths, claude=claude)
    if json_output:
        payload["ok"] = _status_checks_ok(payload)
        _emit_json(payload)
        return 0
    state = StateStore(paths).load()
    jobs = JobStore(paths).list_jobs()

    print("Claude Session Scheduler status")
    print(f"Claude Code: {'OK ' + claude if claude else 'missing'}")
    print(f"Claude login: {_auth_check_detail(_auth_from_payload(payload))}")
    print(f"Next observed reset: {state.get('next_reset_at', 'unknown')}")
    print(f"Next estimated reset: {state.get('next_estimated_reset_at', 'unknown')}")
    print(f"Jobs: {len(jobs)}")
    if jobs:
        print()
        print("Recent jobs:")
        for job in jobs[-5:]:
            last = job.get("last_status", "never")
            print(
                f"  {job['id']}  {job.get('name', '')}  "
                f"{job.get('status', '')}/{last}  "
                f"{format_schedule(job.get('schedule', {}))}"
            )
    print()
    print(f"State: {paths.data_dir}")
    print(f"Logs: {paths.logs_dir}")
    print(f"LaunchAgents: {paths.launch_agents_dir}")
    return 0


def _auth_from_payload(payload: dict[str, Any]) -> ClaudeAuthCheck:
    claude = payload.get("claude", {})
    return ClaudeAuthCheck(
        authenticated=claude.get("authenticated"),
        auth_method=claude.get("auth_method"),
        error=claude.get("auth_error"),
    )


def _run_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ok": result.exit_code == 0,
        "result": {
            "status": result.status,
            "exit_code": result.exit_code,
            "log_path": str(result.log_path),
            "reset": result.reset_info,
            "message": result.message,
            "claude_response_summary": result.claude_response_summary,
        },
    }


def window_start_at_reset(args: argparse.Namespace, paths: AppPaths) -> int:
    state = StateStore(paths).load()
    reset_at = state.get("next_reset_at")
    if not reset_at:
        raise ValueError("no observed Claude reset time is stored")
    target = (
        datetime.fromisoformat(reset_at) + timedelta(minutes=args.buffer_minutes)
    ).astimezone()
    schedule_value = target.strftime("%Y-%m-%d %H:%M")
    schedule = parse_once(schedule_value, now=datetime.now().astimezone())
    job = _build_job(
        "start-window-at-reset",
        args.cwd,
        MINIMAL_WINDOW_PROMPT,
        schedule,
    )
    manager = LaunchdManager(paths)
    result = manager.install(job, dry_run=args.dry_run)
    payload = {
        "ok": True,
        "job": _job_payload(job),
        "launchd": {
            "label": result.label,
            "path": str(result.plist_path),
            "plist": result.plist,
            "loaded": result.loaded,
        },
    }
    if args.dry_run:
        if _args_wants_json(args):
            _emit_json(payload)
            return 0
        print(
            json.dumps(
                {"job": job, "launchd": {"path": str(result.plist_path), "plist": result.plist}},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    JobStore(paths).add(job)
    if _args_wants_json(args):
        _emit_json(payload)
        return 0
    print(f"scheduled {job['id']} for {job['schedule']['run_at']}")
    return 0


def command_logs(args: argparse.Namespace, paths: AppPaths) -> int:
    paths.ensure()
    if args.job_id:
        logs = sorted(paths.logs_dir.glob(f"{args.job_id}-*.log"))
        if not logs:
            raise ValueError(f"no logs for job: {args.job_id}")
        latest = logs[-1]
        if args.json:
            _emit_json(
                {
                    "ok": True,
                    "job_id": args.job_id,
                    "log": {
                        "path": str(latest),
                        "content": latest.read_text(encoding="utf-8"),
                    },
                }
            )
            return 0
        print(latest)
        print(latest.read_text(encoding="utf-8"))
        return 0
    logs = sorted(paths.logs_dir.glob("*.log"), key=lambda path: path.stat().st_mtime)
    if args.json:
        _emit_json({"ok": True, "logs": [str(path) for path in logs[-20:]]})
        return 0
    if not logs:
        print("No logs.")
        return 0
    for path in logs[-20:]:
        print(path)
    return 0
