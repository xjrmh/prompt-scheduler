import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from claude_session_scheduler.paths import AppPaths
from claude_session_scheduler.runner import run_job
from claude_session_scheduler.storage import JobStore, StateStore, utc_now_iso


def make_paths(tmp: str) -> AppPaths:
    root = Path(tmp)
    return AppPaths(root / "state", root / "agents")


def write_fake_claude(directory: Path, body: str) -> Path:
    executable = directory / "claude"
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
            updated = JobStore(paths).get(job["id"])
            self.assertEqual(updated["run_count"], 1)
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
