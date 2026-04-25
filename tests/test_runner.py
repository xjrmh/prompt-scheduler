import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from prompt_scheduler.paths import AppPaths
from prompt_scheduler.runner import run_job
from prompt_scheduler.storage import JobStore, StateStore, utc_now_iso


def make_paths(tmp: str) -> AppPaths:
    root = Path(tmp)
    return AppPaths(root / "state", root / "agents")


def write_fake_claude(directory: Path, body: str) -> Path:
    executable = directory / "claude"
    executable.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def write_fake_codex(directory: Path, body: str) -> Path:
    executable = directory / "codex"
    executable.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def make_job(tmp: str, prompt: str = "hello") -> dict:
    return {
        "id": "job-1234",
        "name": "test",
        "cwd": tmp,
        "prompt": prompt,
        "schedule": {"type": "daily", "time": "09:00"},
        "status": "scheduled",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "run_count": 0,
    }


class RunnerTests(unittest.TestCase):
    def test_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(bin_dir, "echo '{\"result\":\"ok\"}'")
            job = make_job(tmp)
            JobStore(paths).add(job)
            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.claude_response_summary, "ok")
            updated = JobStore(paths).get(job["id"])
            self.assertEqual(updated["run_count"], 1)
            self.assertEqual(updated["last_claude_response_summary"], "ok")
            self.assertTrue(Path(updated["last_log_path"]).exists())

    def test_successful_run_records_estimated_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(bin_dir, "echo '{\"result\":\"ok\"}'")
            job = make_job(tmp)
            JobStore(paths).add(job)
            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )
            self.assertEqual(result.status, "success")
            state = StateStore(paths).load()
            started = datetime.fromisoformat(state["last_estimated_window_started_at"])
            reset = datetime.fromisoformat(state["next_estimated_reset_at"])
            self.assertEqual(reset - started, timedelta(hours=5))

    def test_successful_codex_run_uses_output_last_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            args_path = Path(tmp) / "codex-args.txt"
            fake = write_fake_codex(
                bin_dir,
                f"""
if [ "$1" = "login" ]; then
  echo 'Logged in using ChatGPT'
  exit 0
fi
printf '%s\\n' "$@" > "{args_path}"
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-last-message" ]; then
    shift
    output="$1"
  fi
  shift
done
printf 'Codex OK\\n' > "$output"
""",
            )
            job = make_job(tmp)
            job["provider"] = "codex"
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                codex_bin=str(fake),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.provider, "codex")
            self.assertEqual(result.claude_response_summary, "Codex OK")
            updated = JobStore(paths).get(job["id"])
            self.assertEqual(updated["last_response_summary"], "Codex OK")
            self.assertEqual(updated["last_claude_response_summary"], "Codex OK")
            self.assertNotIn("next_estimated_reset_at", StateStore(paths).load())
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[:3], ["--ask-for-approval", "never", "exec"])
            self.assertIn("--model", args)
            self.assertEqual(args[args.index("--model") + 1], "gpt-5.4-mini")

    def test_codex_model_override_threads_into_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            args_path = Path(tmp) / "codex-args.txt"
            fake = write_fake_codex(
                bin_dir,
                f"""
if [ "$1" = "login" ]; then
  echo 'Logged in using ChatGPT'
  exit 0
fi
printf '%s\\n' "$@" > "{args_path}"
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-last-message" ]; then
    shift
    output="$1"
  fi
  shift
done
printf 'Codex OK\\n' > "$output"
""",
            )
            job = make_job(tmp)
            job["provider"] = "codex"
            job["codex_model"] = "gpt-5.3-codex"
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                codex_bin=str(fake),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "success")
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[args.index("--model") + 1], "gpt-5.3-codex")

    def test_claude_model_override_threads_into_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            args_path = Path(tmp) / "claude-args.txt"
            fake = write_fake_claude(
                bin_dir,
                f"""
printf '%s\\n' "$@" > "{args_path}"
echo '{{"result":"ok"}}'
""",
            )
            job = make_job(tmp)
            job["claude_model"] = "haiku"
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "success")
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertIn("--model", args)
            self.assertEqual(args[args.index("--model") + 1], "haiku")

    def test_claude_run_omits_model_flag_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            args_path = Path(tmp) / "claude-args.txt"
            fake = write_fake_claude(
                bin_dir,
                f"""
printf '%s\\n' "$@" > "{args_path}"
echo '{{"result":"ok"}}'
""",
            )
            job = make_job(tmp)
            JobStore(paths).add(job)

            run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )

            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertNotIn("--model", args)

    def test_successful_codex_run_records_rate_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_codex(
                bin_dir,
                """
if [ "$1" = "login" ]; then
  echo 'Logged in using ChatGPT'
  exit 0
fi
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-last-message" ]; then
    shift
    output="$1"
  fi
  shift
done
printf 'Codex OK\\n' > "$output"
""",
            )

            codex_home = Path(tmp) / "codex-home"
            day_dir = codex_home / "sessions" / "2026" / "04" / "24"
            day_dir.mkdir(parents=True)
            primary_at = 1777072414
            secondary_at = 1777400497
            event = json.dumps(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {"resets_at": primary_at, "window_minutes": 300, "used_percent": 23.0},
                            "secondary": {"resets_at": secondary_at, "window_minutes": 10080, "used_percent": 91.0},
                            "plan_type": "prolite",
                        },
                    },
                }
            )
            (day_dir / "rollout-x.jsonl").write_text(event + "\n", encoding="utf-8")

            job = make_job(tmp)
            job["provider"] = "codex"
            JobStore(paths).add(job)

            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(codex_home)
            try:
                result = run_job(
                    job["id"],
                    paths=paths,
                    codex_bin=str(fake),
                    cleanup_launchd=False,
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

            self.assertEqual(result.status, "success")
            state = StateStore(paths).load()
            expected_primary = datetime.fromtimestamp(primary_at, tz=timezone.utc).isoformat()
            expected_secondary = datetime.fromtimestamp(secondary_at, tz=timezone.utc).isoformat()
            self.assertEqual(state["codex_next_reset_at"], expected_primary)
            self.assertEqual(state["codex_weekly_reset_at"], expected_secondary)
            self.assertEqual(state["codex_rate_limits"]["plan_type"], "prolite")
            self.assertIn("codex_rate_limits_updated_at", state)

    def test_both_provider_run_sends_to_codex_and_claude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_claude = write_fake_claude(
                bin_dir,
                """
if [ "$1" = "auth" ]; then
  echo '{"loggedIn":true,"authMethod":"claude.ai"}'
  exit 0
fi
echo '{"result":"Claude OK"}'
""",
            )
            fake_codex = write_fake_codex(
                bin_dir,
                """
if [ "$1" = "login" ]; then
  echo 'Logged in using ChatGPT'
  exit 0
fi
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-last-message" ]; then
    shift
    output="$1"
  fi
  shift
done
printf 'Codex OK\\n' > "$output"
""",
            )
            job = make_job(tmp)
            job["provider"] = "both"
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake_claude),
                codex_bin=str(fake_codex),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.provider, "both")
            self.assertEqual(len(result.provider_results or ()), 2)
            self.assertIn("Codex: Codex OK", result.claude_response_summary or "")
            self.assertIn("Claude Code: Claude OK", result.claude_response_summary or "")
            updated = JobStore(paths).get(job["id"])
            self.assertEqual(updated["provider"], "both")
            self.assertEqual(updated["run_count"], 1)
            self.assertIn("Codex: Codex OK", updated["last_response_summary"])
            self.assertIn("Claude Code: Claude OK", updated["last_response_summary"])

    def test_usage_limit_records_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(
                bin_dir,
                "echo 'Claude usage limit reached. Resets at 5:00 PM.' >&2\nexit 1",
            )
            job = make_job(tmp)
            JobStore(paths).add(job)
            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )
            self.assertEqual(result.status, "usage_limit")
            self.assertEqual(result.exit_code, 1)
            state = StateStore(paths).load()
            self.assertIn("next_reset_at", state)

    def test_current_usage_limit_message_records_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(
                bin_dir,
                "echo '{\"api_error_status\":429,\"result\":\"You'\\''ve hit your limit \\u00b7 resets 12pm (America/New_York)\"}'\nexit 1",
            )
            job = make_job(tmp)
            JobStore(paths).add(job)
            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )
            self.assertEqual(result.status, "usage_limit")
            state = StateStore(paths).load()
            self.assertIn("next_reset_at", state)

    def test_auth_required_prevents_prompt_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(
                bin_dir,
                """
if [ "$1" = "auth" ]; then
  echo '{"loggedIn":false}'
  exit 0
fi
echo 'should not send prompt'
exit 0
""",
            )
            job = make_job(tmp)
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "auth_required")
            self.assertIn("Claude login required", result.message or "")
            updated = JobStore(paths).get(job["id"])
            self.assertEqual(updated["last_status"], "auth_required")
            self.assertIn("Claude login required", updated["last_stderr_summary"])

    def test_auth_required_detected_from_send_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = write_fake_claude(
                bin_dir,
                """
if [ "$1" = "auth" ]; then
  echo '{"unexpected":"shape"}'
  exit 0
fi
echo 'Please log in with claude auth login' >&2
exit 1
""",
            )
            job = make_job(tmp)
            JobStore(paths).add(job)

            result = run_job(
                job["id"],
                paths=paths,
                claude_bin=str(fake),
                cleanup_launchd=False,
            )

            self.assertEqual(result.status, "auth_required")

    def test_missing_claude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            job = make_job(tmp)
            JobStore(paths).add(job)
            old_path = os.environ.get("PATH", "")
            try:
                os.environ["PATH"] = str(Path(tmp) / "empty-bin")
                with patch("prompt_scheduler.runner.find_provider_executable", return_value=None):
                    result = run_job(job["id"], paths=paths, cleanup_launchd=False)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.exit_code, 127)

    def test_invalid_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(tmp)
            job = make_job(str(Path(tmp) / "missing"))
            JobStore(paths).add(job)
            result = run_job(job["id"], paths=paths, cleanup_launchd=False)
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.exit_code, 1)
            self.assertIn("cwd does not exist", result.message or "")


if __name__ == "__main__":
    unittest.main()
