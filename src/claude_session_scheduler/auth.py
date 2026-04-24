from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


AUTH_STATUS_TIMEOUT_SECONDS = 10
AUTH_REQUIRED_EXIT_CODE = 78


@dataclass(frozen=True)
class ClaudeAuthCheck:
    authenticated: bool | None
    auth_method: str | None = None
    error: str | None = None


def looks_like_auth_required(output: str) -> bool:
    value = output.lower()
    auth_terms = (
        "not logged in",
        "not signed in",
        "not authenticated",
        "login required",
        "authentication required",
        "auth required",
        "please log in",
        "please login",
        "run claude auth login",
        "claude auth login",
        "invalid api key",
        "missing api key",
        "oauth token",
    )
    return any(term in value for term in auth_terms)


def check_claude_auth(
    claude_bin: str | None,
    *,
    timeout_seconds: int = AUTH_STATUS_TIMEOUT_SECONDS,
) -> ClaudeAuthCheck:
    if not claude_bin:
        return ClaudeAuthCheck(
            authenticated=None,
            error="Claude Code is not installed.",
        )

    try:
        completed = subprocess.run(
            [claude_bin, "auth", "status", "--json"],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return ClaudeAuthCheck(
            authenticated=None,
            error="Claude Code executable was not found.",
        )
    except subprocess.TimeoutExpired:
        return ClaudeAuthCheck(
            authenticated=None,
            error="Claude auth status timed out.",
        )
    except OSError as exc:
        return ClaudeAuthCheck(
            authenticated=None,
            error=str(exc),
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = f"{stdout}\n{stderr}".strip()
    payload = _decode_json_object(stdout)
    if payload is not None:
        logged_in = payload.get("loggedIn")
        auth_method = _string_value(payload.get("authMethod") or payload.get("apiProvider"))
        if logged_in is True:
            return ClaudeAuthCheck(authenticated=True, auth_method=auth_method)
        if logged_in is False:
            return ClaudeAuthCheck(
                authenticated=False,
                auth_method=auth_method,
                error="Claude login required. Run `claude auth login`.",
            )

    if looks_like_auth_required(combined):
        return ClaudeAuthCheck(
            authenticated=False,
            error="Claude login required. Run `claude auth login`.",
        )

    if completed.returncode != 0:
        return ClaudeAuthCheck(
            authenticated=None,
            error=combined or f"Claude auth status exited with code {completed.returncode}.",
        )

    return ClaudeAuthCheck(
        authenticated=None,
        error="Claude auth status did not report login state.",
    )


def _decode_json_object(value: str) -> dict[str, object] | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
