from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


RESET_PREFIX = r"(?:resets?|reset|refills?|available|replenished)"
TIMEZONE_SUFFIX = r"(?:\s*\(([A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)+)\))?"


def _now() -> datetime:
    return datetime.now().astimezone()


def _localize(dt: datetime, now: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=now.tzinfo)
    return dt.astimezone(now.tzinfo)


def _relevant_message(text: str) -> str:
    for line in text.splitlines():
        lower = line.lower()
        if "limit" in lower or "reset" in lower or "refill" in lower:
            return line.strip()[:500]
    return text.strip().replace("\n", " ")[:500]


def _parse_datetime_value(value: str, now: datetime) -> datetime | None:
    value = value.strip().rstrip(".,;)")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    normalized = value.replace("T", " ")
    formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %I %p",
    ]
    for fmt in formats:
        try:
            return _localize(datetime.strptime(normalized, fmt), now)
        except ValueError:
            continue
    try:
        return _localize(datetime.fromisoformat(value), now)
    except ValueError:
        return None


def _future_time_today_or_tomorrow(
    hour: int,
    minute: int,
    meridiem: str | None,
    now: datetime,
    timezone_name: str | None = None,
) -> datetime:
    if meridiem:
        meridiem = meridiem.lower().replace(".", "")
        if hour < 1 or hour > 12:
            raise ValueError("invalid 12-hour clock value")
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    reference = now
    if timezone_name:
        try:
            reference = now.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            reference = now
    candidate = datetime.combine(
        reference.date(), time(hour=hour, minute=minute)
    ).replace(tzinfo=reference.tzinfo)
    if candidate <= reference:
        candidate += timedelta(days=1)
    return candidate.astimezone(now.tzinfo)


def parse_reset_time(text: str, now: datetime | None = None) -> dict[str, Any] | None:
    if not text.strip():
        return None
    now = now or _now()
    compact = " ".join(text.split())

    datetime_pattern = re.compile(
        RESET_PREFIX
        + r".{0,60}?\b(?:at|on)\s+"
        + r"(\d{4}-\d{2}-\d{2}[ T]\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s?[AP]M|[+-]\d{2}:?\d{2}|Z)?)",
        re.IGNORECASE,
    )
    match = datetime_pattern.search(compact)
    if match:
        parsed = _parse_datetime_value(match.group(1), now)
        if parsed is not None:
            return {
                "next_reset_at": parsed.isoformat(),
                "source": "claude-output",
                "confidence": "observed",
                "last_limit_message": _relevant_message(text),
            }

    time_pattern = re.compile(
        RESET_PREFIX
        + r".{0,60}?\b(?:at|around)?\s+"
        + r"(\d{1,2})(?::(\d{2}))?\s*([AP]\.?M\.?)\b"
        + TIMEZONE_SUFFIX,
        re.IGNORECASE,
    )
    match = time_pattern.search(compact)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        parsed = _future_time_today_or_tomorrow(
            hour, minute, match.group(3), now, match.group(4)
        )
        return {
            "next_reset_at": parsed.isoformat(),
            "source": "claude-output",
            "confidence": "observed",
            "last_limit_message": _relevant_message(text),
        }

    hour24_pattern = re.compile(
        RESET_PREFIX
        + r".{0,60}?\b(?:at|around)?\s+"
        + r"([01]?\d|2[0-3]):([0-5]\d)\b"
        + TIMEZONE_SUFFIX,
        re.IGNORECASE,
    )
    match = hour24_pattern.search(compact)
    if match:
        parsed = _future_time_today_or_tomorrow(
            int(match.group(1)), int(match.group(2)), None, now, match.group(3)
        )
        return {
            "next_reset_at": parsed.isoformat(),
            "source": "claude-output",
            "confidence": "observed",
            "last_limit_message": _relevant_message(text),
        }

    return None


def looks_like_usage_limit(text: str) -> bool:
    lower = text.lower()
    return (
        "usage limit reached" in lower
        or "limit reached" in lower
        or "hit your limit" in lower
        or "rate limit" in lower
        or '"api_error_status":429' in lower.replace(" ", "")
        or ("usage limit" in lower and "reset" in lower and "reached" in lower)
        or ("usage limit" in lower and "exceeded" in lower)
    )
