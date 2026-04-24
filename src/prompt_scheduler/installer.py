from __future__ import annotations

import shutil
import subprocess

from .providers import CLAUDE, CODEX, provider_spec


CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
CLAUDE_INSTALL_COMMAND = ["npm", "install", "-g", CLAUDE_CODE_PACKAGE]
CODEX_PACKAGE = "@openai/codex"
CODEX_INSTALL_COMMAND = ["npm", "install", "-g", CODEX_PACKAGE]


class ProviderInstallError(RuntimeError):
    pass


ClaudeInstallError = ProviderInstallError


def _node_major_version(node_bin: str) -> int:
    result = subprocess.run(
        [node_bin, "--version"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ProviderInstallError(f"could not read Node.js version: {detail}")
    version = result.stdout.strip().lstrip("v")
    try:
        return int(version.split(".", 1)[0])
    except (IndexError, ValueError) as exc:
        raise ProviderInstallError(f"could not parse Node.js version: {version}") from exc


def validate_provider_install_prerequisites(provider: str = CLAUDE) -> tuple[str, str]:
    spec = provider_spec(provider)
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")
    if not node_bin:
        raise ProviderInstallError(
            f"Node.js 18+ is required to install {spec.label} with npm."
        )
    if not npm_bin:
        raise ProviderInstallError(f"npm is required to install {spec.label}.")
    major = _node_major_version(node_bin)
    if major < 18:
        raise ProviderInstallError(
            f"Node.js 18+ is required; found Node.js {major}."
        )
    return node_bin, npm_bin


def validate_claude_install_prerequisites() -> tuple[str, str]:
    return validate_provider_install_prerequisites(CLAUDE)


def validate_codex_install_prerequisites() -> tuple[str, str]:
    return validate_provider_install_prerequisites(CODEX)


def install_provider(provider: str, *, quiet: bool = False) -> None:
    spec = provider_spec(provider)
    _, npm_bin = validate_provider_install_prerequisites(spec.name)
    command = [npm_bin, "install", "-g", spec.install_package]
    result = subprocess.run(command, capture_output=quiet, text=quiet)
    if result.returncode != 0:
        raise ProviderInstallError(
            f"{spec.label} install failed. Try running without sudo: "
            + " ".join(spec.install_command)
        )


def install_claude_code(*, quiet: bool = False) -> None:
    install_provider(CLAUDE, quiet=quiet)


def install_codex(*, quiet: bool = False) -> None:
    install_provider(CODEX, quiet=quiet)
