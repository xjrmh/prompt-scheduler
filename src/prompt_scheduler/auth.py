from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .providers import CLAUDE, CODEX, login_command_text, provider_spec


AUTH_STATUS_TIMEOUT_SECONDS = 10
AUTH_REQUIRED_EXIT_CODE = 78


@dataclass(frozen=True)
class AuthCheck:
    authenticated: bool | None
    auth_method: str | None = None
    error: str | None = None


ClaudeAuthCheck = AuthCheck


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
        "run codex login",
        "codex login",
        "invalid api key",
        "missing api key",
        "oauth token",
    )
    return any(term in value for term in auth_terms)


def check_claude_auth(
    claude_bin: str | None,
    *,
    timeout_seconds: int = AUTH_STATUS_TIMEOUT_SECONDS,
) -> AuthCheck:
    if not claude_bin:
        return AuthCheck(
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
        return AuthCheck(
            authenticated=None,
            error="Claude Code executable was not found.",
        )
    except subprocess.TimeoutExpired:
        return AuthCheck(
            authenticated=None,
            error="Claude auth status timed out.",
        )
    except OSError as exc:
        return AuthCheck(
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
            return AuthCheck(authenticated=True, auth_method=auth_method)
        if logged_in is False:
            return AuthCheck(
                authenticated=False,
                auth_method=auth_method,
                error="Claude login required. Run `claude auth login`.",
            )

    if looks_like_auth_required(combined):
        return AuthCheck(
            authenticated=False,
            error="Claude login required. Run `claude auth login`.",
        )

    if completed.returncode != 0:
        return AuthCheck(
            authenticated=None,
            error=combined or f"Claude auth status exited with code {completed.returncode}.",
        )

    return AuthCheck(
        authenticated=None,
        error="Claude auth status did not report login state.",
    )


def check_codex_auth(
    codex_bin: str | None,
    *,
    timeout_seconds: int = AUTH_STATUS_TIMEOUT_SECONDS,
) -> AuthCheck:
    if not codex_bin:
        return AuthCheck(
            authenticated=None,
            error="Codex is not installed.",
        )

    try:
        completed = subprocess.run(
            [codex_bin, "login", "status"],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return AuthCheck(
            authenticated=None,
            error="Codex executable was not found.",
        )
    except subprocess.TimeoutExpired:
        return AuthCheck(
            authenticated=None,
            error="Codex login status timed out.",
        )
    except OSError as exc:
        return AuthCheck(authenticated=None, error=str(exc))

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = f"{stdout}\n{stderr}".strip()
    lowered = combined.lower()
    if completed.returncode == 0 and "logged in" in lowered:
        auth_method = None
        marker = "using "
        if marker in lowered:
            start = lowered.index(marker) + len(marker)
            auth_method = combined[start:].strip() or None
        return AuthCheck(authenticated=True, auth_method=auth_method)

    if looks_like_auth_required(combined) or "not logged in" in lowered:
        return AuthCheck(
            authenticated=False,
            error="Codex login required. Run `codex login`.",
        )

    if completed.returncode != 0:
        return AuthCheck(
            authenticated=None,
            error=combined or f"Codex login status exited with code {completed.returncode}.",
        )

    return AuthCheck(
        authenticated=None,
        error="Codex login status did not report login state.",
    )


def check_provider_auth(
    provider: str,
    executable: str | None,
    *,
    timeout_seconds: int = AUTH_STATUS_TIMEOUT_SECONDS,
) -> AuthCheck:
    normalized = provider_spec(provider).name
    if normalized == CLAUDE:
        return check_claude_auth(executable, timeout_seconds=timeout_seconds)
    if normalized == CODEX:
        return check_codex_auth(executable, timeout_seconds=timeout_seconds)
    spec = provider_spec(normalized)
    return AuthCheck(
        authenticated=None,
        error=f"{spec.label} login status is not supported. Run `{login_command_text(spec.name)}`.",
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
