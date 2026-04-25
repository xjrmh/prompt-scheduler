from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import codex_rate_limits
from .auth import AuthCheck, ClaudeAuthCheck, check_provider_auth
from .ids import make_job_id
from .installer import (
    ClaudeInstallError,
    install_provider,
    validate_provider_install_prerequisites,
)
from .launchd import LaunchdError, LaunchdManager
from .paths import AppPaths
from .providers import (
    BOTH,
    CLAUDE,
    CODEX,
    PROVIDER_SPECS,
    SEND_PROVIDER_CHOICES,
    SUPPORTED_PROVIDERS,
    find_provider_executable,
    login_command_text,
    normalize_provider,
    normalize_provider_selection,
    provider_label,
    provider_spec,
)
from .runner import (
    MINIMAL_WINDOW_PROMPT,
    RunnerError,
    extract_response_summary,
    run_inline_prompt,
    run_job,
)
from .schedules import (
    INTERVAL_CHOICES,
    ScheduleError,
    format_schedule,
    parse_interval,
    parse_once,
    parse_schedule,
)
from .storage import JobStore, StateStore, utc_now_iso


DEFAULT_PROJECT_FOLDER_NAME = "Prompt Scheduler Project"
STATUSLINE_COMMAND = "python3 -m prompt_scheduler statusline"
RATE_LIMIT_WINDOWS = ("five_hour", "seven_day")
PROVIDER_ENV_VAR = "PROMPT_SCHEDULER_PROVIDER"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-scheduler",
        description="Schedule local Claude Code or Codex prompts with macOS launchd.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Set up Prompt Scheduler.")
    _add_provider_arg(setup, include_auto=True)
    _add_install_flags(setup)
    _add_json_flag(setup)

    doctor = subparsers.add_parser("doctor", help="Check local prerequisites.")
    _add_provider_arg(doctor, include_auto=True)
    _add_install_flags(doctor)
    _add_json_flag(doctor)

    top_add = subparsers.add_parser("add", help="Add a scheduled prompt.")
    _add_provider_arg(top_add, include_both=True)
    _add_schedule_args(top_add, required=False)
    _add_model_args(top_add)
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
        "start-now", help="Start a provider session by sending a tiny OK prompt."
    )
    _add_provider_arg(start_now, include_auto=True, include_both=True)
    start_now.add_argument("--cwd", default=None)
    _add_model_args(start_now)
    _add_json_flag(start_now)

    start_reset = subparsers.add_parser(
        "start-at-reset", help="Schedule the minimal prompt at the observed reset time."
    )
    _add_provider_arg(start_reset, include_both=True)
    start_reset.add_argument("--cwd", default=None)
    start_reset.add_argument("--buffer-minutes", type=int, default=2)
    start_reset.add_argument("--dry-run", action="store_true")
    _add_model_args(start_reset)
    _add_json_flag(start_reset)

    wake_loop = subparsers.add_parser(
        "wake-loop",
        help="Manage a recurring wake-up prompt that fires every 30 min, 1 h, or 2 h.",
    )
    wake_loop_sub = wake_loop.add_subparsers(dest="wake_loop_command", required=True)
    wake_loop_start = wake_loop_sub.add_parser(
        "start", help="Install the recurring wake-up prompt."
    )
    _add_provider_arg(wake_loop_start, include_both=True)
    wake_loop_start.add_argument("--cwd", required=True)
    wake_loop_start.add_argument(
        "--every",
        required=True,
        choices=tuple(INTERVAL_CHOICES),
        help="Wake-up interval: 30m, 1h, or 2h.",
    )
    wake_loop_start.add_argument(
        "--prompt",
        required=True,
        help="Prompt text to send on each interval.",
    )
    wake_loop_start.add_argument("--dry-run", action="store_true")
    _add_model_args(wake_loop_start)
    _add_json_flag(wake_loop_start)
    wake_loop_stop = wake_loop_sub.add_parser(
        "stop", help="Remove the recurring wake-up prompt if installed."
    )
    _add_json_flag(wake_loop_stop)

    schedule = subparsers.add_parser("schedule", help="Manage scheduled jobs.")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    add = schedule_sub.add_parser("add", help="Add a scheduled prompt.")
    _add_provider_arg(add, include_both=True)
    _add_schedule_args(add, required=True)
    _add_model_args(add)
    _add_json_flag(add)

    nested_list = schedule_sub.add_parser("list", help="List jobs.")
    _add_json_flag(nested_list)
    remove = schedule_sub.add_parser("remove", help="Remove a scheduled job.")
    remove.add_argument("job_id")
    _add_json_flag(remove)

    run = subparsers.add_parser("run", help="Run a job by id.")
    run.add_argument("job_id")

    window = subparsers.add_parser("window", help="Start provider usage windows.")
    window_sub = window.add_subparsers(dest="window_command", required=True)
    start_now = window_sub.add_parser(
        "start-now", help="Start a provider session by sending a tiny OK prompt."
    )
    _add_provider_arg(start_now, include_auto=True, include_both=True)
    start_now.add_argument("--cwd", required=True)
    _add_model_args(start_now)
    _add_json_flag(start_now)
    start_reset = window_sub.add_parser(
        "start-at-reset", help="Schedule the minimal prompt at the observed reset time."
    )
    _add_provider_arg(start_reset, include_both=True)
    start_reset.add_argument("--cwd", required=True)
    start_reset.add_argument("--buffer-minutes", type=int, default=2)
    start_reset.add_argument("--dry-run", action="store_true")
    _add_model_args(start_reset)
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
        help="Install the selected provider without prompting if it is missing.",
    )
    install.add_argument(
        "--no-install",
        action="store_true",
        help="Only report missing providers; do not prompt to install one.",
    )


def _add_provider_arg(
    parser: argparse.ArgumentParser,
    *,
    include_auto: bool = False,
    include_both: bool = False,
) -> None:
    provider_choices = SEND_PROVIDER_CHOICES if include_both else SUPPORTED_PROVIDERS
    choices = ("auto",) + provider_choices if include_auto else provider_choices
    parser.add_argument(
        "--provider",
        choices=choices,
        default="auto" if include_auto else None,
        help=(
            "Prompt provider to use."
            if not include_auto
            else "Prompt provider to use, or auto to prefer an authenticated provider."
        ),
    )


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON response.",
    )


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--claude-model",
        default=None,
        help="Override the Claude Code model (e.g. opus, sonnet, haiku, or a full model id).",
    )
    parser.add_argument(
        "--codex-model",
        default=None,
        help="Override the Codex model (e.g. gpt-5.4-mini, gpt-5.3-codex, gpt-5.4).",
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
                provider_selection=args.provider,
                assume_yes=args.yes,
                prompt_install=not args.no_install,
                json_output=args.json,
            )
        if args.command == "doctor":
            return command_doctor(
                paths,
                provider_selection=args.provider,
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
            return command_start_now(
                args.cwd or str(Path.cwd()),
                paths,
                provider_selection=args.provider,
                json_output=args.json,
                claude_model=getattr(args, "claude_model", None),
                codex_model=getattr(args, "codex_model", None),
            )
        if args.command == "start-at-reset":
            if args.cwd is None:
                args.cwd = str(Path.cwd())
            return window_start_at_reset(args, paths)
        if args.command == "wake-loop":
            return command_wake_loop(args, paths)
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
            "`prompt-scheduler install-statusline --force` to replace it."
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


def _provider_from_env(*, include_both: bool = False) -> str | None:
    value = os.environ.get(PROVIDER_ENV_VAR)
    if not value:
        return None
    provider = value.strip().lower()
    choices = SEND_PROVIDER_CHOICES if include_both else SUPPORTED_PROVIDERS
    if provider in choices:
        return provider
    return None


def _provider_for_new_job(requested: str | None) -> str:
    if requested:
        return normalize_provider_selection(requested, default=CLAUDE)
    return _provider_from_env(include_both=True) or CLAUDE


def _provider_executables() -> dict[str, str | None]:
    return {
        provider: find_provider_executable(provider)
        for provider in PROVIDER_SPECS
    }


def _provider_status(provider: str, executable: str | None) -> dict[str, Any]:
    auth = check_provider_auth(provider, executable)
    return {
        "available": executable is not None,
        "path": executable,
        "authenticated": auth.authenticated,
        "auth_method": auth.auth_method,
        "auth_error": auth.error,
        "login_command": login_command_text(provider),
        "install_command": " ".join(provider_spec(provider).install_command),
        "label": provider_spec(provider).label,
    }


def _provider_is_ready(status: dict[str, Any] | None) -> bool:
    return bool(status and status.get("available") and status.get("authenticated") is True)


def _choose_active_provider(
    providers: dict[str, dict[str, Any]],
    requested: str | None = "auto",
) -> str:
    if requested and requested != "auto":
        return normalize_provider(requested, default=CLAUDE)

    env_provider = _provider_from_env()
    if env_provider and env_provider in providers:
        return env_provider

    for provider in (CODEX, CLAUDE):
        if _provider_is_ready(providers.get(provider)):
            return provider
    for provider in (CODEX, CLAUDE):
        if providers.get(provider, {}).get("available"):
            return provider
    return CLAUDE


def _active_provider_status(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload.get("active_provider") or CLAUDE
    providers = payload.get("providers") or {}
    status = providers.get(provider)
    if isinstance(status, dict):
        return status
    legacy = payload.get("claude")
    return legacy if isinstance(legacy, dict) else {}


def _provider_ready_from_payload(payload: dict[str, Any]) -> bool:
    providers = payload.get("providers") or {}
    if isinstance(providers, dict):
        return any(_provider_is_ready(status) for status in providers.values())
    return _provider_is_ready(payload.get("claude"))


def _resolve_run_provider(
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
) -> str:
    if provider_selection and provider_selection != "auto":
        return normalize_provider_selection(provider_selection, default=CLAUDE)
    env_provider = _provider_from_env(include_both=True)
    if env_provider == BOTH:
        return BOTH
    payload = _status_payload(paths, provider_selection=provider_selection)
    return normalize_provider(payload.get("active_provider"), default=CLAUDE)


def command_doctor(
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
    assume_yes: bool = False,
    prompt_install: bool = True,
    json_output: bool = False,
) -> int:
    paths.ensure()
    executables = _provider_executables()
    launchctl = shutil.which("launchctl")
    if json_output:
        payload = _status_payload(
            paths,
            provider_selection=provider_selection,
            executables=executables,
            launchctl=launchctl,
        )
        active_provider = payload["active_provider"]
        active_status = _active_provider_status(payload)
        if (
            not active_status.get("available")
            and prompt_install
            and assume_yes
            and _maybe_install_provider_json(active_provider)
        ):
            executables = _provider_executables()
            payload = _status_payload(
                paths,
                provider_selection=provider_selection,
                executables=executables,
                launchctl=launchctl,
            )
        ok = _status_checks_ok(payload)
        payload["ok"] = ok
        active_status = _active_provider_status(payload)
        active_provider = payload["active_provider"]
        if not active_status.get("available"):
            payload["next_commands"] = [
                f"prompt-scheduler doctor --provider {active_provider} --yes"
            ]
        elif active_status.get("authenticated") is not True:
            payload["next_commands"] = [login_command_text(active_provider)]
        _emit_json(payload)
        return 0 if ok else 1

    payload = _status_payload(
        paths,
        provider_selection=provider_selection,
        executables=executables,
        launchctl=launchctl,
    )
    ok = _print_doctor_checks(payload)

    active_provider = payload["active_provider"]
    active_status = _active_provider_status(payload)
    if not active_status.get("available") and prompt_install:
        installed = _maybe_install_provider(
            active_provider,
            assume_yes=assume_yes,
            noninteractive_command=f"prompt-scheduler doctor --provider {active_provider} --yes",
        )
        if installed:
            executables = _provider_executables()
            launchctl = shutil.which("launchctl")
            print()
            payload = _status_payload(
                paths,
                provider_selection=provider_selection,
                executables=executables,
                launchctl=launchctl,
            )
            ok = _print_doctor_checks(payload)

    return 0 if ok else 1


def command_setup(
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
    assume_yes: bool = False,
    prompt_install: bool = True,
    json_output: bool = False,
) -> int:
    if json_output:
        return command_setup_json(
            paths,
            provider_selection=provider_selection,
            assume_yes=assume_yes,
            prompt_install=prompt_install,
        )

    print("Prompt Scheduler setup")
    print()
    paths.ensure()
    executables = _provider_executables()
    launchctl = shutil.which("launchctl")
    payload = _status_payload(
        paths,
        provider_selection=provider_selection,
        executables=executables,
        launchctl=launchctl,
    )
    ok = _print_doctor_checks(payload)

    active_provider = payload["active_provider"]
    active_status = _active_provider_status(payload)
    if not active_status.get("available") and prompt_install:
        installed = _maybe_install_provider(
            active_provider,
            assume_yes=assume_yes,
            noninteractive_command=f"prompt-scheduler setup --provider {active_provider} --yes",
        )
        if installed:
            executables = _provider_executables()
            launchctl = shutil.which("launchctl")
            print()
            payload = _status_payload(
                paths,
                provider_selection=provider_selection,
                executables=executables,
                launchctl=launchctl,
            )
            ok = _print_doctor_checks(payload)

    jobs = JobStore(paths).list_jobs()
    if not sys.stdin.isatty():
        print()
        print("Next commands:")
        if not ok:
            active_provider = payload["active_provider"]
            print(f"  prompt-scheduler setup --provider {active_provider} --yes")
        print("  prompt-scheduler add")
        print("  prompt-scheduler status")
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
        print("Create one later with: prompt-scheduler add")
    elif ok:
        print()
        print(f"Setup complete. {len(jobs)} job(s) configured.")
        print("Run `prompt-scheduler status` for an overview.")
    else:
        print()
        print("Fix the missing checks above, then run `prompt-scheduler setup` again.")

    return 0 if ok else 1


def command_setup_json(
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
    assume_yes: bool = False,
    prompt_install: bool = True,
) -> int:
    paths.ensure()
    executables = _provider_executables()
    launchctl = shutil.which("launchctl")
    payload = _status_payload(
        paths,
        provider_selection=provider_selection,
        executables=executables,
        launchctl=launchctl,
    )
    active_provider = payload["active_provider"]
    active_status = _active_provider_status(payload)
    if not active_status.get("available") and prompt_install and assume_yes:
        installed = _maybe_install_provider_json(active_provider)
        if not installed:
            payload["ok"] = False
            payload["error"] = f"{provider_spec(active_provider).label} install failed"
            _emit_json(payload)
            return 1
        executables = _provider_executables()
        payload = _status_payload(
            paths,
            provider_selection=provider_selection,
            executables=executables,
            launchctl=launchctl,
        )
    ok = _status_checks_ok(payload)
    payload["ok"] = ok
    active_provider = payload["active_provider"]
    active_status = _active_provider_status(payload)
    if not active_status.get("available"):
        payload["next_commands"] = [
            f"prompt-scheduler setup --provider {active_provider} --yes"
        ]
    elif active_status.get("authenticated") is not True:
        payload["next_commands"] = [login_command_text(active_provider)]
    elif not payload["jobs"]:
        payload["next_commands"] = ["prompt-scheduler add"]
    _emit_json(payload)
    return 0 if ok else 1


def _print_doctor_checks(payload: dict[str, Any]) -> bool:
    checks = []
    checks_payload = payload["checks"]
    checks.append(("platform macOS", checks_payload["platform_macos"], sys.platform))
    providers = payload["providers"]
    for provider in SUPPORTED_PROVIDERS:
        status = providers[provider]
        label = provider_spec(provider).label
        checks.append(
            (
                f"{label} executable",
                status["available"],
                status["path"] or "missing",
            )
        )
        auth_ok = status.get("authenticated") is True
        checks.append((f"{label} login", auth_ok, _auth_check_detail(status)))
    checks.append(
        (
            "active provider ready",
            _provider_is_ready(_active_provider_status(payload)),
            provider_spec(payload["active_provider"]).label,
        )
    )
    checks.append(
        (
            "launchctl",
            checks_payload["launchctl"],
            checks_payload["launchctl_path"] or "missing",
        )
    )
    checks.append(("data dir", checks_payload["data_dir"], payload["paths"]["state"]))
    checks.append(
        (
            "LaunchAgents dir",
            checks_payload["launch_agents_dir"],
            payload["paths"]["launch_agents"],
        )
    )

    ok = True
    for label, passed, detail in checks:
        if label.endswith(" executable") or label.endswith(" login"):
            passed_for_ok = True
        else:
            passed_for_ok = passed
        ok = ok and passed_for_ok
        status = "OK" if passed else "MISSING"
        print(f"{status:7} {label}: {detail}")
    return ok


def _auth_check_detail(auth: AuthCheck | dict[str, Any]) -> str:
    authenticated = auth.authenticated if isinstance(auth, AuthCheck) else auth.get("authenticated")
    auth_method = auth.auth_method if isinstance(auth, AuthCheck) else auth.get("auth_method")
    error = auth.error if isinstance(auth, AuthCheck) else auth.get("auth_error")
    if authenticated is True:
        if auth_method:
            return f"signed in via {auth_method}"
        return "signed in"
    if authenticated is False:
        return error or "sign in required"
    return error or "unknown"


def _maybe_install_provider(
    provider: str, *, assume_yes: bool, noninteractive_command: str
) -> bool:
    spec = provider_spec(provider)
    command_text = " ".join(spec.install_command)
    print()
    print(f"{spec.label} is required to run scheduled prompts with this provider.")
    print(f"Official npm install command: {command_text}")

    try:
        validate_provider_install_prerequisites(spec.name)
    except ClaudeInstallError as exc:
        print(f"Cannot install automatically: {exc}", file=sys.stderr)
        print(f"Install manually with: {command_text}", file=sys.stderr)
        return False

    if not assume_yes:
        if not sys.stdin.isatty():
            print(
                f"Run `{noninteractive_command}` to install {spec.label}.",
                file=sys.stderr,
            )
            return False
        answer = input(f"Install {spec.label} now? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print(f"{spec.label} install skipped.")
            return False

    print(f"Installing {spec.label}...")
    install_provider(spec.name)
    print(f"{spec.label} install command finished.")
    return True


def _maybe_install_claude(*, assume_yes: bool, noninteractive_command: str) -> bool:
    return _maybe_install_provider(
        CLAUDE,
        assume_yes=assume_yes,
        noninteractive_command=noninteractive_command,
    )


def _maybe_install_provider_json(provider: str) -> bool:
    try:
        validate_provider_install_prerequisites(provider)
        install_provider(provider, quiet=True)
    except ClaudeInstallError:
        return False
    return True


def _maybe_install_claude_json() -> bool:
    return _maybe_install_provider_json(CLAUDE)


def _status_checks_ok(payload: dict[str, Any]) -> bool:
    checks = payload["checks"]
    return bool(
        checks["platform_macos"]
        and _provider_is_ready(_active_provider_status(payload))
        and checks["launchctl"]
        and checks["data_dir"]
        and checks["launch_agents_dir"]
    )


def _reset_for_provider(state: dict[str, Any], provider: str) -> str | None:
    if provider == CLAUDE:
        return state.get("next_reset_at")
    if provider == CODEX:
        return state.get("codex_next_reset_at")
    if provider == BOTH:
        claude_at = state.get("next_reset_at")
        codex_at = state.get("codex_next_reset_at")
        if claude_at and codex_at:
            try:
                later = max(
                    datetime.fromisoformat(claude_at),
                    datetime.fromisoformat(codex_at),
                )
            except ValueError:
                return claude_at
            return later.isoformat()
        return claude_at or codex_at
    return None


def _refresh_codex_rate_limits_into_state(paths: AppPaths) -> None:
    rate_limits = codex_rate_limits.latest_rate_limits()
    if rate_limits is None:
        return
    StateStore(paths).record_codex_rate_limits(
        codex_rate_limits.to_state_payload(rate_limits)
    )


def _status_payload(
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
    executables: dict[str, str | None] | None = None,
    claude: str | None = None,
    launchctl: str | None = None,
) -> dict[str, Any]:
    paths.ensure()
    if executables is None:
        executables = _provider_executables()
    if claude is not None:
        executables[CLAUDE] = claude
    if launchctl is None:
        launchctl = shutil.which("launchctl")
    providers = {
        provider: _provider_status(provider, executables.get(provider))
        for provider in SUPPORTED_PROVIDERS
    }
    active_provider = _choose_active_provider(providers, requested=provider_selection)
    jobs = [_job_payload(job) for job in JobStore(paths).list_jobs()]
    _refresh_codex_rate_limits_into_state(paths)
    state = StateStore(paths).load()
    launch_agents_ok = paths.launch_agents_dir.exists() or paths.launch_agents_dir.parent.exists()
    ok = bool(
        sys.platform == "darwin"
        and _provider_is_ready(providers.get(active_provider))
        and launchctl
        and launch_agents_ok
    )
    return {
        "ok": ok,
        "active_provider": active_provider,
        "active_provider_label": provider_spec(active_provider).label,
        "providers": providers,
        "claude": providers[CLAUDE],
        "codex": providers[CODEX],
        "reset": {
            "next_reset_at": state.get("next_reset_at"),
            "next_estimated_reset_at": state.get("next_estimated_reset_at"),
            "last_estimated_window_started_at": state.get(
                "last_estimated_window_started_at"
            ),
            "rate_limits": state.get("rate_limits"),
            "rate_limits_updated_at": state.get("rate_limits_updated_at"),
            "reset_source": state.get("reset_source"),
            "codex_next_reset_at": state.get("codex_next_reset_at"),
            "codex_weekly_reset_at": state.get("codex_weekly_reset_at"),
            "codex_rate_limits": state.get("codex_rate_limits"),
            "codex_rate_limits_updated_at": state.get("codex_rate_limits_updated_at"),
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
            "launchctl_path": launchctl,
            "data_dir": paths.data_dir.exists(),
            "launch_agents_dir": launch_agents_ok,
        },
    }


def _job_payload(job: dict[str, Any]) -> dict[str, Any]:
    schedule = job.get("schedule", {})
    provider = normalize_provider_selection(job.get("provider"), default=CLAUDE)
    response_summary = job.get("last_response_summary") or job.get(
        "last_claude_response_summary"
    )
    if not response_summary and provider != BOTH:
        response_summary = extract_response_summary(
            job.get("last_stdout_summary") or "",
            provider=provider,
        )
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "cwd": job.get("cwd"),
        "provider": provider,
        "provider_label": provider_label(provider),
        "claude_model": job.get("claude_model"),
        "codex_model": job.get("codex_model"),
        "schedule": schedule,
        "schedule_label": format_schedule(schedule),
        "status": job.get("status"),
        "last_status": job.get("last_status"),
        "last_run_at": job.get("last_run_at"),
        "last_log_path": job.get("last_log_path"),
        "last_response_summary": response_summary,
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


def _build_job(
    name: str,
    cwd: str,
    prompt: str,
    schedule: dict[str, Any],
    *,
    provider: str = CLAUDE,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> dict[str, Any]:
    cwd_path = Path(cwd).expanduser()
    if not cwd_path.is_dir():
        raise ValueError(f"cwd does not exist or is not a directory: {cwd_path}")
    provider = normalize_provider_selection(provider, default=CLAUDE)
    job: dict[str, Any] = {
        "id": make_job_id(name),
        "name": name,
        "cwd": str(cwd_path.resolve()),
        "prompt": prompt,
        "provider": provider,
        "schedule": schedule,
        "status": "scheduled",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "run_count": 0,
    }
    if claude_model:
        job["claude_model"] = claude_model
    if codex_model:
        job["codex_model"] = codex_model
    return job


def schedule_add(
    args: argparse.Namespace, paths: AppPaths, *, interactive: bool = False
) -> int:
    name, cwd, prompt, schedule = _resolve_add_inputs(args, interactive=interactive)
    requested_provider = getattr(args, "provider", None)
    if interactive and not requested_provider and sys.stdin.isatty():
        provider = _prompt_for_provider(_provider_for_new_job(None))
    else:
        provider = _provider_for_new_job(requested_provider)
    job = _build_job(
        name,
        cwd,
        prompt,
        schedule,
        provider=provider,
        claude_model=getattr(args, "claude_model", None),
        codex_model=getattr(args, "codex_model", None),
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
                + ". Run `prompt-scheduler add` in an interactive terminal "
                "or provide flags such as `prompt-scheduler add --name "
                '"morning" --daily "09:00" --prompt "..."`.'
            )
        print("Create a prompt schedule")
        print()
        cwd = _prompt_with_default("Project folder", cwd)
        if not name:
            name = _prompt_required("Schedule name")
        if not schedule_supplied:
            at, daily, weekly = _prompt_for_schedule()
        if not prompt:
            prompt = _prompt_required("Prompt")

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


def _prompt_for_provider(default: str) -> str:
    default = normalize_provider_selection(default, default=CLAUDE)
    while True:
        value = input(f"Provider [codex/claude/both] ({default}): ").strip().lower()
        if not value:
            return default
        if value in SEND_PROVIDER_CHOICES:
            return value
        print("Choose codex, claude, or both.")


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
        return command_start_now(
            args.cwd,
            paths,
            provider_selection=args.provider,
            json_output=args.json,
            claude_model=getattr(args, "claude_model", None),
            codex_model=getattr(args, "codex_model", None),
        )
    if args.window_command == "start-at-reset":
        return window_start_at_reset(args, paths)
    raise ValueError(f"unknown window command: {args.window_command}")


def command_start_now(
    cwd: str,
    paths: AppPaths,
    *,
    provider_selection: str | None = "auto",
    json_output: bool = False,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> int:
    provider = _resolve_run_provider(paths, provider_selection=provider_selection)
    result = run_inline_prompt(
        cwd=cwd,
        paths=paths,
        provider=provider,
        claude_model=claude_model,
        codex_model=codex_model,
    )
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
    payload = _status_payload(paths)
    if json_output:
        payload["ok"] = _status_checks_ok(payload)
        _emit_json(payload)
        return 0
    state = StateStore(paths).load()
    jobs = JobStore(paths).list_jobs()

    print("Prompt Scheduler status")
    for provider in SUPPORTED_PROVIDERS:
        status = payload["providers"][provider]
        label = provider_spec(provider).label
        path = status["path"]
        print(f"{label}: {'OK ' + path if path else 'missing'}")
        print(f"{label} login: {_auth_check_detail(status)}")
    print(f"Active provider: {payload['active_provider_label']}")
    claude_reset = state.get("next_reset_at")
    codex_reset = state.get("codex_next_reset_at")
    if claude_reset and codex_reset and claude_reset != codex_reset:
        print(f"Next observed Claude reset: {claude_reset}")
        print(f"Next observed Codex reset: {codex_reset}")
    else:
        print(f"Next observed reset: {claude_reset or codex_reset or 'unknown'}")
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
    detail = _run_result_detail_payload(result)
    return {
        "ok": result.exit_code == 0,
        "result": detail,
    }


def _run_result_detail_payload(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "exit_code": result.exit_code,
        "log_path": str(result.log_path),
        "provider": result.provider,
        "provider_label": provider_label(result.provider),
        "reset": result.reset_info,
        "message": result.message,
        "response_summary": result.claude_response_summary,
        "claude_response_summary": result.claude_response_summary,
        "provider_results": [
            _run_result_detail_payload(provider_result)
            for provider_result in (result.provider_results or ())
        ],
    }


def window_start_at_reset(args: argparse.Namespace, paths: AppPaths) -> int:
    provider = _provider_for_new_job(getattr(args, "provider", None))
    state = StateStore(paths).load()
    reset_at = _reset_for_provider(state, provider)
    if not reset_at:
        raise ValueError(
            f"no observed {provider_label(provider)} reset time is stored"
        )
    now = datetime.now().astimezone()
    target = (
        datetime.fromisoformat(reset_at) + timedelta(minutes=args.buffer_minutes)
    ).astimezone()
    if target <= now:
        raise ValueError(
            f"stored {provider_label(provider)} reset {reset_at} has already "
            f"passed; run `prompt-scheduler start-now --provider {provider}` "
            "to begin a session immediately."
        )
    schedule_value = target.strftime("%Y-%m-%d %H:%M")
    schedule = parse_once(schedule_value, now=now)
    job = _build_job(
        "start-window-at-reset",
        args.cwd,
        MINIMAL_WINDOW_PROMPT,
        schedule,
        provider=provider,
        claude_model=getattr(args, "claude_model", None),
        codex_model=getattr(args, "codex_model", None),
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
    _remove_existing_wake_jobs(paths, provider=provider)
    JobStore(paths).add(job)
    if _args_wants_json(args):
        _emit_json(payload)
        return 0
    print(f"scheduled {job['id']} for {job['schedule']['run_at']}")
    return 0


def _remove_existing_wake_jobs(paths: AppPaths, *, provider: str) -> None:
    store = JobStore(paths)
    manager = LaunchdManager(paths)
    for existing in store.list_jobs():
        if existing.get("name") != "start-window-at-reset":
            continue
        if existing.get("provider") != provider:
            continue
        if existing.get("status") != "scheduled":
            continue
        manager.uninstall(existing, ignore_errors=True)
        store.remove(existing["id"])


def _remove_existing_jobs_named(paths: AppPaths, *, name: str) -> list[dict[str, Any]]:
    store = JobStore(paths)
    manager = LaunchdManager(paths)
    removed: list[dict[str, Any]] = []
    for existing in store.list_jobs():
        if existing.get("name") != name:
            continue
        if existing.get("status") != "scheduled":
            continue
        manager.uninstall(existing, ignore_errors=True)
        store.remove(existing["id"])
        removed.append(existing)
    return removed


WAKE_LOOP_JOB_NAME = "wake-loop"


def command_wake_loop(args: argparse.Namespace, paths: AppPaths) -> int:
    if args.wake_loop_command == "start":
        return _wake_loop_start(args, paths)
    if args.wake_loop_command == "stop":
        return _wake_loop_stop(args, paths)
    raise ValueError(f"unknown wake-loop command: {args.wake_loop_command}")


def _wake_loop_start(args: argparse.Namespace, paths: AppPaths) -> int:
    provider = _provider_for_new_job(getattr(args, "provider", None))
    schedule = parse_interval(args.every)
    job = _build_job(
        WAKE_LOOP_JOB_NAME,
        args.cwd,
        args.prompt,
        schedule,
        provider=provider,
        claude_model=getattr(args, "claude_model", None),
        codex_model=getattr(args, "codex_model", None),
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
                {
                    "job": job,
                    "launchd": {"path": str(result.plist_path), "plist": result.plist},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    _remove_existing_jobs_named(paths, name=WAKE_LOOP_JOB_NAME)
    JobStore(paths).add(job)
    if _args_wants_json(args):
        _emit_json(payload)
        return 0
    print(f"scheduled {job['id']} every {schedule['every']}")
    return 0


def _wake_loop_stop(args: argparse.Namespace, paths: AppPaths) -> int:
    removed = _remove_existing_jobs_named(paths, name=WAKE_LOOP_JOB_NAME)
    if _args_wants_json(args):
        _emit_json(
            {
                "ok": True,
                "removed": _job_payload(removed[0]) if removed else None,
            }
        )
        return 0
    if not removed:
        print("no wake-loop is installed")
        return 0
    for job in removed:
        print(f"removed {job['id']}")
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
