from __future__ import annotations

import re
from datetime import datetime
from typing import Any


class ScheduleError(ValueError):
    pass


DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}
LAUNCHD_WEEKDAYS = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


def _now() -> datetime:
    return datetime.now().astimezone()


def parse_time(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{2}:\d{2}", value.strip()):
        raise ScheduleError("time must use HH:MM format")
    hour_s, minute_s = value.split(":", 1)
    hour = int(hour_s)
    minute = int(minute_s)
    if hour > 23 or minute > 59:
        raise ScheduleError("time must be a valid 24-hour clock value")
    return hour, minute


def parse_once(value: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    try:
        run_at = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ScheduleError("one-time schedule must use YYYY-MM-DD HH:MM") from exc
    run_at = run_at.replace(tzinfo=now.tzinfo)
    if run_at <= now:
        raise ScheduleError("one-time schedule must be in the future")
    return {"type": "once", "run_at": run_at.isoformat()}


def parse_daily(value: str) -> dict[str, Any]:
    hour, minute = parse_time(value)
    return {"type": "daily", "time": f"{hour:02d}:{minute:02d}"}


def _parse_day_name(value: str) -> str:
    key = value.strip().lower()[:3]
    if key not in DAY_ORDER:
        raise ScheduleError(f"invalid weekday: {value}")
    return key


def _expand_day_segment(segment: str) -> list[str]:
    if "-" not in segment:
        return [_parse_day_name(segment)]
    start_s, end_s = segment.split("-", 1)
    start = _parse_day_name(start_s)
    end = _parse_day_name(end_s)
    start_i = DAY_ORDER.index(start)
    end_i = DAY_ORDER.index(end)
    if start_i <= end_i:
        return DAY_ORDER[start_i : end_i + 1]
    return DAY_ORDER[start_i:] + DAY_ORDER[: end_i + 1]


def parse_weekly(value: str) -> dict[str, Any]:
    parts = value.strip().split()
    if len(parts) != 2:
        raise ScheduleError('weekly schedule must look like "Mon-Fri 09:00"')
    days_part, time_part = parts
    hour, minute = parse_time(time_part)
    days: list[str] = []
    for segment in days_part.split(","):
        if not segment.strip():
            raise ScheduleError("weekly day list contains an empty segment")
        for day in _expand_day_segment(segment):
            if day not in days:
                days.append(day)
    return {
        "type": "weekly",
        "days": [LAUNCHD_WEEKDAYS[day] for day in days],
        "day_names": [DAY_LABELS[day] for day in days],
        "time": f"{hour:02d}:{minute:02d}",
    }


def parse_schedule(
    *, at: str | None = None, daily: str | None = None, weekly: str | None = None
) -> dict[str, Any]:
    selected = [value is not None for value in (at, daily, weekly)].count(True)
    if selected != 1:
        raise ScheduleError("choose exactly one of --at, --daily, or --weekly")
    if at is not None:
        return parse_once(at)
    if daily is not None:
        return parse_daily(daily)
    if weekly is not None:
        return parse_weekly(weekly)
    raise ScheduleError("missing schedule")


def schedule_to_start_calendar(schedule: dict[str, Any]) -> Any:
    schedule_type = schedule.get("type")
    if schedule_type == "once":
        run_at = datetime.fromisoformat(schedule["run_at"])
        return {
            "Month": run_at.month,
            "Day": run_at.day,
            "Hour": run_at.hour,
            "Minute": run_at.minute,
        }
    if schedule_type == "daily":
        hour, minute = parse_time(schedule["time"])
        return {"Hour": hour, "Minute": minute}
    if schedule_type == "weekly":
        hour, minute = parse_time(schedule["time"])
        return [
            {"Weekday": int(day), "Hour": hour, "Minute": minute}
            for day in schedule["days"]
        ]
    raise ScheduleError(f"unsupported schedule type: {schedule_type}")


def is_due(job: dict[str, Any], now: datetime | None = None) -> bool:
    schedule = job.get("schedule", {})
    if schedule.get("type") != "once":
        return True
    now = now or _now()
    run_at = datetime.fromisoformat(schedule["run_at"])
    return now >= run_at


def is_terminal_once_status(status: str | None) -> bool:
    return status in {
        "completed",
        "failed",
        "partial_success",
        "usage_limit",
        "auth_required",
        "timed_out",
    }


def format_schedule(schedule: dict[str, Any]) -> str:
    schedule_type = schedule.get("type")
    if schedule_type == "once":
        return f"once at {schedule['run_at']}"
    if schedule_type == "daily":
        return f"daily at {schedule['time']}"
    if schedule_type == "weekly":
        days = ",".join(schedule.get("day_names", [str(d) for d in schedule["days"]]))
        return f"weekly {days} at {schedule['time']}"
    if schedule_type == "manual":
        return "manual"
    return str(schedule)
