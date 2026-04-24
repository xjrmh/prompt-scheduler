from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


ProviderName = str

CLAUDE = "claude"
CODEX = "codex"
SUPPORTED_PROVIDERS = (CLAUDE, CODEX)


@dataclass(frozen=True)
class ProviderSpec:
    name: ProviderName
    label: str
    executable: str
    login_command: tuple[str, ...]
    install_package: str
    fallback_paths: tuple[str, ...] = ()

    @property
    def install_command(self) -> tuple[str, ...]:
        return ("npm", "install", "-g", self.install_package)


PROVIDER_SPECS: dict[ProviderName, ProviderSpec] = {
    CLAUDE: ProviderSpec(
        name=CLAUDE,
        label="Claude Code",
        executable="claude",
        login_command=("claude", "auth", "login"),
        install_package="@anthropic-ai/claude-code",
        fallback_paths=(
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            "~/.local/bin/claude",
        ),
    ),
    CODEX: ProviderSpec(
        name=CODEX,
        label="Codex",
        executable="codex",
        login_command=("codex", "login"),
        install_package="@openai/codex",
        fallback_paths=(
            "/Applications/Codex.app/Contents/Resources/codex",
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            "~/.local/bin/codex",
        ),
    ),
}


def normalize_provider(value: object, *, default: ProviderName = CLAUDE) -> ProviderName:
    if isinstance(value, str):
        provider = value.strip().lower()
        if provider in PROVIDER_SPECS:
            return provider
    if default in PROVIDER_SPECS:
        return default
    return CLAUDE


def provider_spec(provider: object, *, default: ProviderName = CLAUDE) -> ProviderSpec:
    return PROVIDER_SPECS[normalize_provider(provider, default=default)]


def login_command_text(provider: object, *, default: ProviderName = CLAUDE) -> str:
    return " ".join(provider_spec(provider, default=default).login_command)


def find_provider_executable(provider: object, *, default: ProviderName = CLAUDE) -> str | None:
    spec = provider_spec(provider, default=default)
    env_name = f"PROMPT_SCHEDULER_{spec.name.upper()}_BIN"
    override = os.environ.get(env_name)
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    from_path = shutil.which(spec.executable)
    if from_path:
        return from_path

    for candidate in spec.fallback_paths:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None
