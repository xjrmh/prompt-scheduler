from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from prompt_scheduler.auth import ClaudeAuthCheck
from prompt_scheduler.cli import DEFAULT_PROJECT_FOLDER_NAME
from prompt_scheduler.cli import main
from prompt_scheduler.paths import AppPaths
from prompt_scheduler.storage import JobStore, StateStore, utc_now_iso


class CliTests(unittest.TestCase):
    def _env(self, root: Path) -> dict[str, str]:
        return {
            "PROMPT_SCHEDULER_HOME": str(root / "state"),
            "PROMPT_SCHEDULER_LAUNCH_AGENTS_DIR": str(root / "agents"),
            "HOME": str(root / "home"),
        }

    def _auth_ok(self) -> ClaudeAuthCheck:
        return ClaudeAuthCheck(authenticated=True, auth_method="claude.ai")

    def _auth_required(self) -> ClaudeAuthCheck:
        return ClaudeAuthCheck(
            authenticated=False,
            error="Claude login required. Run `claude auth login`.",
        )

    def _auth_for_provider(self, provider: str, executable: str | None) -> ClaudeAuthCheck:
        if executable:
            if provider == "codex":
                return ClaudeAuthCheck(authenticated=True, auth_method="ChatGPT")
            return self._auth_ok()
        if provider == "codex":
            return ClaudeAuthCheck(authenticated=None, error="Codex is not installed.")
        return ClaudeAuthCheck(authenticated=None, error="Claude Code is not installed.")

    def _which_claude_and_launchctl(self, name: str) -> str | None:
        if name == "claude":
            return "/usr/local/bin/claude"
        if name == "launchctl":
            return "/bin/launchctl"
        return None

    def _which_codex_and_launchctl(self, name: str) -> str | None:
        if name == "codex":
            return "/usr/local/bin/codex"
        if name == "launchctl":
            return "/bin/launchctl"
        return None

    def _find_no_provider(self, provider: str) -> str | None:
        return None

    def _find_claude_provider(self, provider: str) -> str | None:
        return "/usr/local/bin/claude" if provider == "claude" else None

    def _find_codex_provider(self, provider: str) -> str | None:
        return "/usr/local/bin/codex" if provider == "codex" else None

    def test_schedule_add_dry_run_outputs_job_and_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(
                    [
                        "schedule",
                        "add",
                        "--name",
                        "daily",
                        "--cwd",
                        tmp,
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["schedule"], {"type": "daily", "time": "09:00"})
            self.assertFalse((root / "agents").exists())

    def test_window_start_at_reset_dry_run_uses_stored_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            agents_dir = root / "agents"
            paths = AppPaths(state_dir, agents_dir)
            reset_at = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
            StateStore(paths).save({"next_reset_at": reset_at})
            out = StringIO()
            with patch.dict(
                "os.environ",
                self._env(root),
            ), redirect_stdout(out):
                code = main(
                    [
                        "window",
                        "start-at-reset",
                        "--cwd",
                        tmp,
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["prompt"], "Reply with exactly OK.")
            self.assertEqual(payload["job"]["schedule"]["type"], "once")

    def test_window_start_at_reset_codex_uses_codex_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            now = datetime.now().astimezone()
            claude_reset = (now + timedelta(hours=4)).replace(microsecond=0)
            codex_reset = (now + timedelta(hours=1)).replace(microsecond=0)
            StateStore(paths).save(
                {
                    "next_reset_at": claude_reset.isoformat(),
                    "codex_next_reset_at": codex_reset.isoformat(),
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(
                    [
                        "window",
                        "start-at-reset",
                        "--cwd",
                        tmp,
                        "--provider",
                        "codex",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["provider"], "codex")
            scheduled = datetime.fromisoformat(payload["job"]["schedule"]["run_at"])
            expected = (codex_reset + timedelta(minutes=2)).astimezone(scheduled.tzinfo).replace(second=0, microsecond=0)
            self.assertEqual(scheduled.replace(second=0, microsecond=0), expected)

    def test_window_start_at_reset_codex_errors_when_codex_reset_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            claude_reset = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
            StateStore(paths).save({"next_reset_at": claude_reset})
            err = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stderr(err):
                code = main(
                    [
                        "window",
                        "start-at-reset",
                        "--cwd",
                        tmp,
                        "--provider",
                        "codex",
                        "--dry-run",
                    ]
                )
            self.assertNotEqual(code, 0)
            self.assertIn("Codex", err.getvalue())

    def test_window_start_at_reset_dedups_same_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            now = datetime.now().astimezone()
            StateStore(paths).save(
                {
                    "next_reset_at": (now + timedelta(hours=4)).isoformat(),
                    "codex_next_reset_at": (now + timedelta(hours=1)).isoformat(),
                }
            )

            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.LaunchdManager"
            ) as launchd_cls:
                launchd_cls.return_value.install.return_value = type(
                    "FakeInstall",
                    (),
                    {"label": "x", "plist_path": Path(tmp) / "p.plist", "plist": "<x/>", "loaded": True},
                )()
                launchd_cls.return_value.uninstall.return_value = None

                first = StringIO()
                with redirect_stdout(first):
                    code1 = main(
                        ["window", "start-at-reset", "--cwd", tmp, "--provider", "codex", "--json"]
                    )
                second = StringIO()
                with redirect_stdout(second):
                    code2 = main(
                        ["window", "start-at-reset", "--cwd", tmp, "--provider", "codex", "--json"]
                    )

            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            jobs = JobStore(paths).list_jobs()
            wake_jobs = [j for j in jobs if j.get("name") == "start-window-at-reset"]
            self.assertEqual(len(wake_jobs), 1)
            self.assertEqual(wake_jobs[0]["provider"], "codex")
            self.assertEqual(wake_jobs[0]["id"], json.loads(second.getvalue())["job"]["id"])

    def test_window_start_at_reset_does_not_dedup_other_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            now = datetime.now().astimezone()
            StateStore(paths).save(
                {
                    "next_reset_at": (now + timedelta(hours=4)).isoformat(),
                    "codex_next_reset_at": (now + timedelta(hours=1)).isoformat(),
                }
            )

            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.LaunchdManager"
            ) as launchd_cls:
                launchd_cls.return_value.install.return_value = type(
                    "FakeInstall",
                    (),
                    {"label": "x", "plist_path": Path(tmp) / "p.plist", "plist": "<x/>", "loaded": True},
                )()
                launchd_cls.return_value.uninstall.return_value = None

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["window", "start-at-reset", "--cwd", tmp, "--provider", "claude", "--json"]),
                        0,
                    )
                    self.assertEqual(
                        main(["window", "start-at-reset", "--cwd", tmp, "--provider", "codex", "--json"]),
                        0,
                    )

            jobs = JobStore(paths).list_jobs()
            wake_jobs = [j for j in jobs if j.get("name") == "start-window-at-reset"]
            self.assertEqual(len(wake_jobs), 2)
            providers = sorted(j["provider"] for j in wake_jobs)
            self.assertEqual(providers, ["claude", "codex"])

    def test_window_start_at_reset_both_uses_later_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            now = datetime.now().astimezone()
            claude_reset = (now + timedelta(hours=4)).replace(microsecond=0)
            codex_reset = (now + timedelta(hours=1)).replace(microsecond=0)
            StateStore(paths).save(
                {
                    "next_reset_at": claude_reset.isoformat(),
                    "codex_next_reset_at": codex_reset.isoformat(),
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(
                    [
                        "window",
                        "start-at-reset",
                        "--cwd",
                        tmp,
                        "--provider",
                        "both",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["provider"], "both")
            scheduled = datetime.fromisoformat(payload["job"]["schedule"]["run_at"])
            expected = (claude_reset + timedelta(minutes=2)).astimezone(scheduled.tzinfo).replace(second=0, microsecond=0)
            self.assertEqual(scheduled.replace(second=0, microsecond=0), expected)

    def test_statusline_records_rate_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            statusline_input = json.dumps(
                {
                    "model": {"display_name": "Sonnet"},
                    "rate_limits": {
                        "five_hour": {
                            "used_percentage": 42.4,
                            "resets_at": 1777068000,
                        },
                        "seven_day": {
                            "used_percentage": 12,
                            "resets_at": 1777500000,
                        },
                    },
                }
            )
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.sys.stdin", StringIO(statusline_input)
            ), redirect_stdout(out):
                code = main(["statusline"])

            self.assertEqual(code, 0)
            self.assertIn("[Sonnet] | 5h 42% fresh", out.getvalue())
            state = StateStore(AppPaths(root / "state", root / "agents")).load()
            self.assertEqual(state["rate_limits"]["five_hour"]["used_percentage"], 42.4)
            self.assertEqual(
                state["next_reset_at"],
                state["rate_limits"]["five_hour"]["resets_at_iso"],
            )
            self.assertEqual(state["reset_source"], "claude-code-statusline")

    def test_install_statusline_writes_claude_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(["install-statusline", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["command"], "python3 -m prompt_scheduler statusline")
            settings = json.loads((root / "home" / ".claude" / "settings.json").read_text())
            self.assertEqual(
                settings["statusLine"],
                {
                    "type": "command",
                    "command": "python3 -m prompt_scheduler statusline",
                },
            )

    def test_install_statusline_requires_force_when_existing_command_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_path = root / "home" / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"statusLine": {"type": "command", "command": "custom"}}),
                encoding="utf-8",
            )
            err = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stderr(err):
                code = main(["install-statusline"])

            self.assertEqual(code, 1)
            self.assertIn("--force", err.getvalue())

    def test_doctor_prompts_and_installs_when_claude_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            installed = {"value": False}

            def fake_which(name: str) -> str | None:
                if name == "claude":
                    return "/usr/local/bin/claude" if installed["value"] else None
                if name == "launchctl":
                    return "/bin/launchctl"
                return None

            def fake_install(provider: str, *, quiet: bool = False) -> None:
                installed["value"] = True

            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return True

            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which", side_effect=fake_which
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=fake_which
            ), patch(
                "prompt_scheduler.cli.validate_provider_install_prerequisites",
                return_value=("/usr/local/bin/node", "/usr/local/bin/npm"),
            ), patch(
                "prompt_scheduler.cli.install_provider", side_effect=fake_install
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), patch(
                "builtins.input", return_value="y"
            ), redirect_stdout(out):
                code = main(["doctor"])

            self.assertEqual(code, 0)
            self.assertTrue(installed["value"])
            self.assertIn("Installing Claude Code", out.getvalue())

    def test_doctor_does_not_prompt_in_non_interactive_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return False

            out = StringIO()
            err = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=lambda name: "/bin/launchctl" if name == "launchctl" else None,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_no_provider
            ), patch(
                "prompt_scheduler.cli.validate_provider_install_prerequisites",
                return_value=("/usr/local/bin/node", "/usr/local/bin/npm"),
            ), patch(
                "prompt_scheduler.cli.install_provider"
            ) as install_mock, patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), redirect_stdout(out), redirect_stderr(err):
                code = main(["doctor"])

            self.assertEqual(code, 1)
            install_mock.assert_not_called()
            self.assertIn("doctor --provider claude --yes", err.getvalue())

    def test_setup_installed_interactive_declines_first_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return True

            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=lambda name: f"/usr/local/bin/{name}",
            ), patch(
                "prompt_scheduler.cli.find_provider_executable",
                side_effect=lambda provider: f"/usr/local/bin/{provider}",
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), patch(
                "builtins.input", return_value="n"
            ), redirect_stdout(out):
                code = main(["setup"])

            self.assertEqual(code, 0)
            self.assertIn("Create one later with", out.getvalue())

    def test_setup_missing_claude_confirmed_installs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            installed = {"value": False}

            def fake_which(name: str) -> str | None:
                if name == "claude":
                    return "/usr/local/bin/claude" if installed["value"] else None
                if name == "launchctl":
                    return "/bin/launchctl"
                return None

            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return True

            def fake_install(provider: str, *, quiet: bool = False) -> None:
                installed["value"] = True

            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which", side_effect=fake_which
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=fake_which
            ), patch(
                "prompt_scheduler.cli.validate_provider_install_prerequisites",
                return_value=("/usr/local/bin/node", "/usr/local/bin/npm"),
            ), patch(
                "prompt_scheduler.cli.install_provider", side_effect=fake_install
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), patch(
                "builtins.input", side_effect=["y", "n"]
            ), redirect_stdout(out):
                code = main(["setup"])

            self.assertEqual(code, 0)
            self.assertTrue(installed["value"])
            self.assertIn("Installing Claude Code", out.getvalue())

    def test_setup_missing_claude_declined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return True

            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=lambda name: "/bin/launchctl" if name == "launchctl" else None,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_no_provider
            ), patch(
                "prompt_scheduler.cli.validate_provider_install_prerequisites",
                return_value=("/usr/local/bin/node", "/usr/local/bin/npm"),
            ), patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), patch(
                "builtins.input", return_value="n"
            ), redirect_stdout(out):
                code = main(["setup"])

            self.assertEqual(code, 1)
            self.assertIn("Claude Code install skipped", out.getvalue())

    def test_setup_non_interactive_does_not_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            class FakeStdin:
                @staticmethod
                def isatty() -> bool:
                    return False

            out = StringIO()
            err = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=lambda name: "/bin/launchctl" if name == "launchctl" else None,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_no_provider
            ), patch(
                "prompt_scheduler.cli.validate_provider_install_prerequisites",
                return_value=("/usr/local/bin/node", "/usr/local/bin/npm"),
            ), patch(
                "prompt_scheduler.cli.install_provider"
            ) as install_mock, patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), redirect_stdout(out), redirect_stderr(err):
                code = main(["setup"])

            self.assertEqual(code, 1)
            install_mock.assert_not_called()
            self.assertIn("prompt-scheduler setup --provider claude --yes", err.getvalue())
            self.assertIn("Next commands", out.getvalue())

    def test_top_level_add_dry_run_defaults_to_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = os.getcwd()
            out = StringIO()
            try:
                os.chdir(tmp)
                with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                    code = main(
                        [
                            "add",
                            "--name",
                            "top",
                            "--daily",
                            "09:00",
                            "--prompt",
                            "hello",
                            "--dry-run",
                        ]
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            expected = root / "home" / DEFAULT_PROJECT_FOLDER_NAME
            self.assertEqual(Path(payload["job"]["cwd"]).resolve(), expected.resolve())
            self.assertTrue(expected.is_dir())

    def test_add_persists_model_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(
                    [
                        "schedule",
                        "add",
                        "--name",
                        "with-models",
                        "--cwd",
                        tmp,
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--provider",
                        "both",
                        "--claude-model",
                        "haiku",
                        "--codex-model",
                        "gpt-5.3-codex",
                        "--dry-run",
                        "--json",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["claude_model"], "haiku")
            self.assertEqual(payload["job"]["codex_model"], "gpt-5.3-codex")

    def test_interactive_add_daily(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_interactive_add(
                tmp,
                ["", "daily-test", "daily", "09:00", "hello", ""],
                {"type": "daily", "time": "09:00"},
            )

    def test_interactive_add_weekly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._interactive_add_payload(
                tmp,
                ["", "weekly-test", "weekly", "Mon-Fri 09:00", "hello", "both"],
            )
            self.assertEqual(payload["job"]["schedule"]["type"], "weekly")
            self.assertEqual(payload["job"]["schedule"]["days"], [1, 2, 3, 4, 5])
            self.assertEqual(payload["job"]["provider"], "both")

    def test_interactive_add_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_at = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
            payload = self._interactive_add_payload(
                tmp,
                ["", "once-test", "once", run_at, "hello", ""],
            )
            self.assertEqual(payload["job"]["schedule"]["type"], "once")

    def _assert_interactive_add(
        self, tmp: str, answers: list[str], expected_schedule: dict[str, str]
    ) -> None:
        payload = self._interactive_add_payload(tmp, answers)
        self.assertEqual(payload["job"]["schedule"], expected_schedule)

    def _interactive_add_payload(self, tmp: str, answers: list[str]) -> dict:
        root = Path(tmp)
        old_cwd = os.getcwd()

        class FakeStdin:
            @staticmethod
            def isatty() -> bool:
                return True

        out = StringIO()
        try:
            os.chdir(tmp)
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.sys.stdin", FakeStdin()
            ), patch(
                "builtins.input", side_effect=answers
            ), redirect_stdout(out):
                code = main(["add", "--dry-run"])
        finally:
            os.chdir(old_cwd)

        self.assertEqual(code, 0)
        payload = json.loads("{" + out.getvalue().split("{", 1)[1])
        self.assertEqual(
            Path(payload["job"]["cwd"]).resolve(),
            (Path(tmp) / "home" / DEFAULT_PROJECT_FOLDER_NAME).resolve(),
        )
        return payload

    def test_top_level_list_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), redirect_stdout(out):
                code = main(["list"])
            self.assertEqual(code, 0)
            self.assertIn("No jobs", out.getvalue())

    def test_status_no_jobs_unknown_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), patch(
                "prompt_scheduler.cli.shutil.which",
                return_value=None,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_no_provider
            ), redirect_stdout(out):
                code = main(["status"])
            self.assertEqual(code, 0)
            self.assertIn("Claude Code: missing", out.getvalue())
            self.assertIn("Next observed reset: unknown", out.getvalue())
            self.assertIn("Next estimated reset: unknown", out.getvalue())
            self.assertIn("Jobs: 0", out.getvalue())

    def test_status_jobs_and_known_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            StateStore(paths).save(
                {
                    "next_reset_at": "2026-04-25T09:00:00-04:00",
                    "next_estimated_reset_at": "2026-04-25T10:00:00-04:00",
                }
            )
            JobStore(paths).add(
                {
                    "id": "job-1234",
                    "name": "morning",
                    "cwd": tmp,
                    "prompt": "hello",
                    "schedule": {"type": "daily", "time": "09:00"},
                    "status": "scheduled",
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                    "run_count": 0,
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=self._which_claude_and_launchctl,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_claude_provider
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), redirect_stdout(out):
                code = main(["status"])
            self.assertEqual(code, 0)
            self.assertIn("Claude Code: OK /usr/local/bin/claude", out.getvalue())
            self.assertIn("Claude Code login: signed in via claude.ai", out.getvalue())
            self.assertIn("Next observed reset: 2026-04-25T09:00:00-04:00", out.getvalue())
            self.assertIn("Next estimated reset: 2026-04-25T10:00:00-04:00", out.getvalue())
            self.assertIn("Jobs: 1", out.getvalue())

    def test_status_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            StateStore(AppPaths(root / "state", root / "agents")).save(
                {
                    "next_reset_at": "2026-04-25T09:00:00-04:00",
                    "next_estimated_reset_at": "2026-04-25T10:00:00-04:00",
                    "last_estimated_window_started_at": "2026-04-25T05:00:00-04:00",
                    "rate_limits": {
                        "five_hour": {
                            "used_percentage": 42,
                            "resets_at_iso": "2026-04-25T09:00:00-04:00",
                        }
                    },
                    "rate_limits_updated_at": "2026-04-25T06:00:00-04:00",
                    "reset_source": "claude-code-statusline",
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=self._which_claude_and_launchctl,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_claude_provider
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), redirect_stdout(out):
                code = main(["status", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["claude"]["available"])
            self.assertTrue(payload["claude"]["authenticated"])
            self.assertEqual(payload["reset"]["next_reset_at"], "2026-04-25T09:00:00-04:00")
            self.assertEqual(
                payload["reset"]["next_estimated_reset_at"],
                "2026-04-25T10:00:00-04:00",
            )
            self.assertEqual(
                payload["reset"]["last_estimated_window_started_at"],
                "2026-04-25T05:00:00-04:00",
            )
            self.assertEqual(payload["reset"]["rate_limits"]["five_hour"]["used_percentage"], 42)
            self.assertEqual(payload["reset"]["reset_source"], "claude-code-statusline")
            self.assertEqual(payload["paths"]["state"], str(root / "state"))

    def test_status_json_uses_codex_when_only_codex_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=self._which_codex_and_launchctl,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_codex_provider
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), redirect_stdout(out):
                code = main(["status", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["active_provider"], "codex")
            self.assertTrue(payload["codex"]["available"])
            self.assertTrue(payload["codex"]["authenticated"])
            self.assertFalse(payload["claude"]["available"])

    def test_status_json_reports_auth_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=self._which_claude_and_launchctl,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_claude_provider
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", return_value=self._auth_required()
            ), redirect_stdout(out):
                code = main(["status", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["claude"]["authenticated"])
            self.assertIn("claude auth login", payload["claude"]["auth_error"])

    def test_status_json_reports_last_claude_response_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            JobStore(paths).add(
                {
                    "id": "job-1234",
                    "name": "Morning",
                    "cwd": tmp,
                    "prompt": "hello",
                    "schedule": {"type": "daily", "time": "09:00"},
                    "status": "scheduled",
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                    "last_stdout_summary": "{\"result\":\"Done\"}\n",
                    "run_count": 1,
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), patch(
                "prompt_scheduler.cli.shutil.which",
                side_effect=self._which_claude_and_launchctl,
            ), patch(
                "prompt_scheduler.cli.find_provider_executable", side_effect=self._find_claude_provider
            ), patch(
                "prompt_scheduler.cli.check_provider_auth", side_effect=self._auth_for_provider
            ), redirect_stdout(out):
                code = main(["status", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["jobs"][0]["last_claude_response_summary"], "Done")

    def test_add_json_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), redirect_stdout(out):
                code = main(
                    [
                        "add",
                        "--name",
                        "json",
                        "--cwd",
                        tmp,
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--dry-run",
                        "--json",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["job"]["name"], "json")
            self.assertEqual(payload["job"]["schedule_label"], "daily at 09:00")
            self.assertFalse(payload["launchd"]["loaded"])

    def test_add_json_dry_run_accepts_codex_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), redirect_stdout(out):
                code = main(
                    [
                        "add",
                        "--provider",
                        "codex",
                        "--name",
                        "codex-json",
                        "--cwd",
                        tmp,
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--dry-run",
                        "--json",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["provider"], "codex")
            self.assertEqual(payload["job"]["provider_label"], "Codex")

    def test_add_json_dry_run_accepts_both_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), redirect_stdout(out):
                code = main(
                    [
                        "add",
                        "--provider",
                        "both",
                        "--name",
                        "both-json",
                        "--cwd",
                        tmp,
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--dry-run",
                        "--json",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["job"]["provider"], "both")
            self.assertEqual(payload["job"]["provider_label"], "Codex + Claude Code")

    def test_remove_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            JobStore(paths).add(
                {
                    "id": "job-1234",
                    "name": "remove-me",
                    "cwd": tmp,
                    "prompt": "hello",
                    "schedule": {"type": "daily", "time": "09:00"},
                    "status": "scheduled",
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                    "run_count": 0,
                }
            )
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(["remove", "job-1234", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["removed"]["id"], "job-1234")

    def test_json_error_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with patch.dict("os.environ", self._env(Path(tmp))), redirect_stdout(out):
                code = main(
                    [
                        "add",
                        "--name",
                        "bad",
                        "--cwd",
                        str(Path(tmp) / "missing"),
                        "--daily",
                        "09:00",
                        "--prompt",
                        "hello",
                        "--json",
                    ]
                )

            self.assertEqual(code, 1)
            payload = json.loads(out.getvalue())
            self.assertFalse(payload["ok"])
            self.assertIn("cwd does not exist", payload["error"])

    def test_logs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            paths.ensure()
            log_path = paths.logs_dir / "job-1234-20260424T090000-0400.log"
            log_path.write_text("status: success\n", encoding="utf-8")
            out = StringIO()
            with patch.dict("os.environ", self._env(root)), redirect_stdout(out):
                code = main(["logs", "job-1234", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["log"]["content"], "status: success\n")


if __name__ == "__main__":
    unittest.main()
