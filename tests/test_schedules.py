from datetime import datetime, timezone
import unittest

from prompt_scheduler.schedules import (
    ScheduleError,
    parse_daily,
    parse_once,
    parse_time,
    parse_weekly,
    schedule_to_start_calendar,
)


class ScheduleTests(unittest.TestCase):
    def test_parse_once_future(self) -> None:
        now = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)
        schedule = parse_once("2026-04-25 09:00", now=now)
        self.assertEqual(schedule["type"], "once")
        self.assertIn("2026-04-25T09:00:00", schedule["run_at"])

    def test_parse_once_rejects_past(self) -> None:
        now = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)
        with self.assertRaises(ScheduleError):
            parse_once("2026-04-24 07:59", now=now)

    def test_parse_daily(self) -> None:
        self.assertEqual(parse_daily("09:30"), {"type": "daily", "time": "09:30"})

    def test_parse_time_rejects_invalid(self) -> None:
        for value in ["9:30", "24:00", "10:60", "soon"]:
            with self.subTest(value=value):
                with self.assertRaises(ScheduleError):
                    parse_time(value)

    def test_parse_weekly_range(self) -> None:
        schedule = parse_weekly("Mon-Fri 09:00")
        self.assertEqual(schedule["days"], [1, 2, 3, 4, 5])
        self.assertEqual(schedule["day_names"], ["Mon", "Tue", "Wed", "Thu", "Fri"])

    def test_parse_weekly_list(self) -> None:
        schedule = parse_weekly("Mon,Wed,Fri 17:30")
        self.assertEqual(schedule["days"], [1, 3, 5])

    def test_parse_weekly_rejects_bad_day(self) -> None:
        with self.assertRaises(ScheduleError):
            parse_weekly("Fun 09:00")

    def test_launchd_calendar_for_weekly(self) -> None:
        schedule = parse_weekly("Mon,Wed 17:30")
        calendar = schedule_to_start_calendar(schedule)
        self.assertEqual(
            calendar,
            [
                {"Weekday": 1, "Hour": 17, "Minute": 30},
                {"Weekday": 3, "Hour": 17, "Minute": 30},
            ],
        )


if __name__ == "__main__":
    unittest.main()
