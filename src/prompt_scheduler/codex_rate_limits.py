from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_MAX_FILES_TO_SCAN = 10


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".codex"


def latest_rate_limits(home: Path | None = None) -> dict[str, Any] | None:
    sessions_dir = (home or codex_home()) / "sessions"
    if not sessions_dir.is_dir():
        return None

    candidates = [path for path in sessions_dir.rglob("rollout-*.jsonl") if path.is_file()]
    if not candidates:
        return None

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for rollout in candidates[:_MAX_FILES_TO_SCAN]:
        rate_limits = _scan_for_rate_limits(rollout)
        if rate_limits is not None:
            return rate_limits
    return None


def to_state_payload(rate_limits: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"codex_rate_limits": rate_limits}

    primary = rate_limits.get("primary")
    if isinstance(primary, dict):
        iso = _epoch_to_iso(primary.get("resets_at"))
        if iso is not None:
            payload["codex_next_reset_at"] = iso

    secondary = rate_limits.get("secondary")
    if isinstance(secondary, dict):
        iso = _epoch_to_iso(secondary.get("resets_at"))
        if iso is not None:
            payload["codex_weekly_reset_at"] = iso

    return payload


def _scan_for_rate_limits(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        rate_limits = _extract_rate_limits(event)
        if rate_limits is not None:
            return rate_limits
    return None


def _extract_rate_limits(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "token_count":
        return None
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None
    if not _has_window_reset(rate_limits):
        return None
    return rate_limits


def _has_window_reset(rate_limits: dict[str, Any]) -> bool:
    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if isinstance(window, dict) and isinstance(window.get("resets_at"), (int, float)):
            return True
    return False


def _epoch_to_iso(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None
