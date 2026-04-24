import tempfile
import unittest
from pathlib import Path

from prompt_scheduler.launchd import LaunchdManager
from prompt_scheduler.paths import AppPaths


class LaunchdTests(unittest.TestCase):
    def test_generate_daily_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            job = {
                "id": "daily-test-1234",
                "schedule": {"type": "daily", "time": "09:00"},
            }
            plist = LaunchdManager(paths).generate_plist(job)
            self.assertEqual(
                plist["Label"],
                "com.local.prompt-scheduler.daily-test-1234",
            )
            self.assertEqual(plist["StartCalendarInterval"], {"Hour": 9, "Minute": 0})
            self.assertEqual(plist["ProgramArguments"][1:4], ["-m", "prompt_scheduler", "run"])
            self.assertIn("PATH", plist["EnvironmentVariables"])

    def test_generate_weekly_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            job = {
                "id": "weekly-test-1234",
                "schedule": {
                    "type": "weekly",
                    "days": [1, 5],
                    "day_names": ["Mon", "Fri"],
                    "time": "17:30",
                },
            }
            plist = LaunchdManager(paths).generate_plist(job)
            self.assertEqual(
                plist["StartCalendarInterval"],
                [
                    {"Weekday": 1, "Hour": 17, "Minute": 30},
                    {"Weekday": 5, "Hour": 17, "Minute": 30},
                ],
            )

    def test_dry_run_install_does_not_write_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            job = {
                "id": "dry-run-1234",
                "schedule": {"type": "daily", "time": "09:00"},
            }
            result = LaunchdManager(paths).install(job, dry_run=True)
            self.assertFalse(result.loaded)
            self.assertFalse(result.plist_path.exists())


if __name__ == "__main__":
    unittest.main()
