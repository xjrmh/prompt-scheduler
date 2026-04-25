from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import AppPaths
from .schedules import schedule_to_start_calendar


LABEL_PREFIX = "com.local.prompt-scheduler"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class LaunchdError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallResult:
    label: str
    plist_path: Path
    plist: dict[str, Any]
    loaded: bool


class LaunchdManager:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def label_for_job(self, job_or_id: dict[str, Any] | str) -> str:
        job_id = job_or_id if isinstance(job_or_id, str) else job_or_id["id"]
        return f"{LABEL_PREFIX}.{job_id}"

    def plist_path_for_job(self, job_or_id: dict[str, Any] | str) -> Path:
        label = self.label_for_job(job_or_id)
        return self.paths.launch_agents_dir / f"{label}.plist"

    def generate_plist(self, job: dict[str, Any]) -> dict[str, Any]:
        env = {"PATH": os.environ.get("PATH", DEFAULT_PATH)}
        if "PYTHONPATH" in os.environ:
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        env.update(self.paths.environment_overrides())
        log_stdout = self.paths.logs_dir / f"{job['id']}.launchd.out.log"
        log_stderr = self.paths.logs_dir / f"{job['id']}.launchd.err.log"
        plist: dict[str, Any] = {
            "Label": self.label_for_job(job),
            "ProgramArguments": [
                sys.executable,
                "-m",
                "prompt_scheduler",
                "run",
                job["id"],
            ],
            "EnvironmentVariables": env,
            "RunAtLoad": False,
            "StandardOutPath": str(log_stdout),
            "StandardErrorPath": str(log_stderr),
        }
        schedule = job["schedule"]
        if schedule.get("type") == "interval":
            plist["StartInterval"] = int(schedule["seconds"])
        else:
            plist["StartCalendarInterval"] = schedule_to_start_calendar(schedule)
        return plist

    def write_plist(self, job: dict[str, Any]) -> Path:
        self.paths.ensure()
        self.paths.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        plist_path = self.plist_path_for_job(job)
        with plist_path.open("wb") as handle:
            plistlib.dump(self.generate_plist(job), handle, sort_keys=True)
        return plist_path

    def install(self, job: dict[str, Any], dry_run: bool = False) -> InstallResult:
        plist = self.generate_plist(job)
        plist_path = self.plist_path_for_job(job)
        if dry_run:
            return InstallResult(
                label=self.label_for_job(job),
                plist_path=plist_path,
                plist=plist,
                loaded=False,
            )

        written_path = self.write_plist(job)
        try:
            self._bootstrap(written_path)
        except Exception:
            written_path.unlink(missing_ok=True)
            raise
        return InstallResult(
            label=self.label_for_job(job),
            plist_path=written_path,
            plist=plist,
            loaded=True,
        )

    def uninstall(
        self, job_or_id: dict[str, Any] | str, ignore_errors: bool = False
    ) -> None:
        plist_path = self.plist_path_for_job(job_or_id)
        errors: list[str] = []
        if sys.platform == "darwin" and shutil.which("launchctl"):
            try:
                self._bootout(plist_path)
            except LaunchdError as exc:
                errors.append(str(exc))
                try:
                    self._legacy_unload(plist_path)
                except LaunchdError as legacy_exc:
                    errors.append(str(legacy_exc))
        plist_path.unlink(missing_ok=True)
        if errors and not ignore_errors:
            raise LaunchdError("; ".join(errors))

    def _launchctl(self) -> str:
        launchctl = shutil.which("launchctl")
        if sys.platform != "darwin":
            raise LaunchdError("launchd install requires macOS; use --dry-run elsewhere")
        if not launchctl:
            raise LaunchdError("launchctl was not found on PATH")
        return launchctl

    def _bootstrap(self, plist_path: Path) -> None:
        launchctl = self._launchctl()
        target = f"gui/{os.getuid()}"
        command = [launchctl, "bootstrap", target, str(plist_path)]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode == 0:
            return
        fallback = subprocess.run(
            [launchctl, "load", str(plist_path)], text=True, capture_output=True
        )
        if fallback.returncode != 0:
            raise LaunchdError(
                "launchctl bootstrap failed: "
                f"{result.stderr.strip() or result.stdout.strip()}; "
                "fallback load failed: "
                f"{fallback.stderr.strip() or fallback.stdout.strip()}"
            )

    def _bootout(self, plist_path: Path) -> None:
        launchctl = self._launchctl()
        target = f"gui/{os.getuid()}"
        result = subprocess.run(
            [launchctl, "bootout", target, str(plist_path)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise LaunchdError(result.stderr.strip() or result.stdout.strip())

    def _legacy_unload(self, plist_path: Path) -> None:
        launchctl = self._launchctl()
        result = subprocess.run(
            [launchctl, "unload", str(plist_path)], text=True, capture_output=True
        )
        if result.returncode != 0:
            raise LaunchdError(result.stderr.strip() or result.stdout.strip())
