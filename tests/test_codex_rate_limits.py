from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prompt_scheduler import codex_rate_limits


def _token_count_event(rate_limits: dict | None) -> str:
    return json.dumps(
        {
            "timestamp": "2026-04-24T19:32:49.740Z",
            "type": "event_msg",
            "payload": {"type": "token_count", "info": None, "rate_limits": rate_limits},
        }
    )


def _other_event() -> str:
    return json.dumps({"type": "event_msg", "payload": {"type": "message", "text": "hi"}})


def _write_rollout(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _sample_rate_limits(primary_resets_at: int = 1777072414, secondary_resets_at: int = 1777400497) -> dict:
    return {
        "limit_id": "codex",
        "limit_name": None,
        "primary": {"used_percent": 23.0, "window_minutes": 300, "resets_at": primary_resets_at},
        "secondary": {"used_percent": 91.0, "window_minutes": 10080, "resets_at": secondary_resets_at},
        "credits": None,
        "plan_type": "prolite",
        "rate_limit_reached_type": None,
    }


class CodexRateLimitsTests(unittest.TestCase):
    def test_returns_none_when_sessions_dir_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(codex_rate_limits.latest_rate_limits(Path(tmp)))

    def test_returns_none_when_no_rollout_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sessions").mkdir()
            self.assertIsNone(codex_rate_limits.latest_rate_limits(Path(tmp)))

    def test_returns_rate_limits_from_latest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            day_dir = home / "sessions" / "2026" / "04" / "24"
            limits = _sample_rate_limits()
            _write_rollout(day_dir / "rollout-old.jsonl", [_token_count_event(_sample_rate_limits(1, 2))])
            time.sleep(0.01)
            _write_rollout(day_dir / "rollout-new.jsonl", [_token_count_event(limits)])

            result = codex_rate_limits.latest_rate_limits(home)
            self.assertEqual(result, limits)

    def test_skips_token_count_with_null_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            day_dir = home / "sessions" / "2026" / "04" / "24"
            usable = _sample_rate_limits()
            null_windows = {"limit_id": "premium", "primary": None, "secondary": None, "plan_type": "prolite"}
            _write_rollout(
                day_dir / "rollout-x.jsonl",
                [_token_count_event(usable), _token_count_event(null_windows)],
            )

            result = codex_rate_limits.latest_rate_limits(home)
            self.assertEqual(result, usable)

    def test_picks_last_token_count_with_rate_limits_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            day_dir = home / "sessions" / "2026" / "04" / "24"
            stale = _sample_rate_limits(100, 200)
            fresh = _sample_rate_limits(300, 400)
            _write_rollout(
                day_dir / "rollout-x.jsonl",
                [
                    _token_count_event(stale),
                    _other_event(),
                    _token_count_event(fresh),
                    _token_count_event(None),
                    _other_event(),
                ],
            )

            result = codex_rate_limits.latest_rate_limits(home)
            self.assertEqual(result, fresh)

    def test_skips_files_without_rate_limits_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            day_dir = home / "sessions" / "2026" / "04" / "24"
            limits = _sample_rate_limits()
            _write_rollout(day_dir / "rollout-old.jsonl", [_token_count_event(limits)])
            time.sleep(0.01)
            _write_rollout(day_dir / "rollout-new.jsonl", [_other_event(), _token_count_event(None)])

            result = codex_rate_limits.latest_rate_limits(home)
            self.assertEqual(result, limits)

    def test_to_state_payload_converts_epoch_to_iso(self) -> None:
        limits = _sample_rate_limits()
        payload = codex_rate_limits.to_state_payload(limits)
        self.assertEqual(payload["codex_rate_limits"], limits)
        primary = datetime.fromisoformat(payload["codex_next_reset_at"])
        secondary = datetime.fromisoformat(payload["codex_weekly_reset_at"])
        self.assertEqual(
            primary, datetime.fromtimestamp(limits["primary"]["resets_at"], tz=timezone.utc)
        )
        self.assertEqual(
            secondary, datetime.fromtimestamp(limits["secondary"]["resets_at"], tz=timezone.utc)
        )

    def test_to_state_payload_handles_missing_fields(self) -> None:
        payload = codex_rate_limits.to_state_payload({"limit_id": "codex"})
        self.assertEqual(payload, {"codex_rate_limits": {"limit_id": "codex"}})

    def test_honors_codex_home_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            day_dir = home / "sessions" / "2026" / "04" / "24"
            limits = _sample_rate_limits()
            _write_rollout(day_dir / "rollout-x.jsonl", [_token_count_event(limits)])

            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(home)
            try:
                result = codex_rate_limits.latest_rate_limits()
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous
            self.assertEqual(result, limits)


if __name__ == "__main__":
    unittest.main()
