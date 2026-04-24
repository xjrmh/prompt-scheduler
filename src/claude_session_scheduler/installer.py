from __future__ import annotations

import shutil
import subprocess


CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
CLAUDE_INSTALL_COMMAND = ["npm", "install", "-g", CLAUDE_CODE_PACKAGE]


class ClaudeInstallError(RuntimeError):
    pass


def _node_major_version(node_bin: str) -> int:
    result = subprocess.run(
        [node_bin, "--version"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ClaudeInstallError(f"could not read Node.js version: {detail}")
    version = result.stdout.strip().lstrip("v")
    try:
        return int(version.split(".", 1)[0])
    except (IndexError, ValueError) as exc:
        raise ClaudeInstallError(f"could not parse Node.js version: {version}") from exc


def validate_claude_install_prerequisites() -> tuple[str, str]:
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")
    if not node_bin:
        raise ClaudeInstallError(
            "Node.js 18+ is required to install Claude Code with npm."
        )
    if not npm_bin:
        raise ClaudeInstallError("npm is required to install Claude Code.")
    major = _node_major_version(node_bin)
    if major < 18:
        raise ClaudeInstallError(
            f"Node.js 18+ is required; found Node.js {major}."
        )
    return node_bin, npm_bin


def install_claude_code(*, quiet: bool = False) -> None:
    _, npm_bin = validate_claude_install_prerequisites()
    command = [npm_bin, "install", "-g", CLAUDE_CODE_PACKAGE]
    result = subprocess.run(command, capture_output=quiet, text=quiet)
    if result.returncode != 0:
        raise ClaudeInstallError(
            "Claude Code install failed. Try running without sudo: "
            + " ".join(CLAUDE_INSTALL_COMMAND)
        )
