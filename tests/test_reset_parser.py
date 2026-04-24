from datetime import datetime, timedelta, timezone
import unittest

from claude_session_scheduler.reset_parser import looks_like_usage_limit, parse_reset_time


class ResetParserTests(unittest.TestCase):
    def test_parse_meridiem_time_today(self) -> None:
        now = datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc)
        parsed = parse_reset_time("Claude usage limit reached. Resets at 5:00 PM.", now=now)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["next_reset_at"], "2026-04-24T17:00:00+00:00")

    def test_parse_meridiem_time_tomorrow_when_past(self) -> None:
        now = datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc)
        parsed = parse_reset_time("Your limit will reset at 1pm", now=now)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["next_reset_at"], "2026-04-25T13:00:00+00:00")

    def test_parse_explicit_datetime(self) -> None:
        now = datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc)
        parsed = parse_reset_time("usage resets at 2026-04-25 09:30", now=now)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["next_reset_at"], "2026-04-25T09:30:00+00:00")

    def test_parse_claude_code_current_limit_message(self) -> None:
        eastern = timezone(timedelta(hours=-4))
        now = datetime(2026, 4, 24, 11, 58, tzinfo=eastern)
        parsed = parse_reset_time(
            "You've hit your limit \u00b7 resets 12pm (America/New_York)", now=now
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["next_reset_at"], "2026-04-24T12:00:00-04:00")

    def test_current_limit_message_is_usage_limit(self) -> None:
        self.assertTrue(
            looks_like_usage_limit(
                '{"api_error_status":429,"result":"You\'ve hit your limit \\u00b7 resets 12pm (America/New_York)"}'
            )
        )

    def test_no_guess_when_no_reset_time(self) -> None:
        self.assertIsNone(parse_reset_time("Approaching usage limit soon."))


if __name__ == "__main__":
    unittest.main()
