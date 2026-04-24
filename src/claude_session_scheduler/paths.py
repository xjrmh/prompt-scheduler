from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "claude-session-scheduler"
HOME_ENV = "CLAUDE_SESSION_SCHEDULER_HOME"
LAUNCH_AGENTS_ENV = "CLAUDE_SESSION_SCHEDULER_LAUNCH_AGENTS_DIR"


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    launch_agents_dir: Path

    @classmethod
    def from_env(cls) -> "AppPaths":
        data_dir = Path(
            os.environ.get(HOME_ENV, Path.home() / ".local" / "share" / APP_NAME)
        ).expanduser()
        launch_agents_dir = Path(
            os.environ.get(
                LAUNCH_AGENTS_ENV, Path.home() / "Library" / "LaunchAgents"
            )
        ).expanduser()
        return cls(data_dir=data_dir, launch_agents_dir=launch_agents_dir)

    @property
    def jobs_path(self) -> Path:
        return self.data_dir / "jobs.json"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def locks_dir(self) -> Path:
        return self.data_dir / "locks"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def environment_overrides(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if HOME_ENV in os.environ:
            env[HOME_ENV] = str(self.data_dir)
        if LAUNCH_AGENTS_ENV in os.environ:
            env[LAUNCH_AGENTS_ENV] = str(self.launch_agents_dir)
        return env
