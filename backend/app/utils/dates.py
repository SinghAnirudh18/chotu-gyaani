"""Relative dates are resolved by code, never by the LLM.

The LLM emits a spec such as {"relative": "next_monday", "time": "10:00"} or
{"date": "2026-11-05", "time": "17:00"}; this module turns it into an aware
datetime in the business timezone and rejects times in the past."""
import calendar
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.exceptions import ValidationFailed

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_TIME = time(10, 0)


def utcnow() -> datetime:
    return datetime.now(UTC)


def today_in(tz: str, now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(ZoneInfo(tz)).date()


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def end_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not m:
        raise ValidationFailed("Invalid time", code="invalid_time", details={"time": value})
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValidationFailed("Invalid time", code="invalid_time", details={"time": value})
    return time(h, mi)


def resolve_relative_date(relative: str, today: date) -> date:
    r = relative.strip().lower()
    if r == "today":
        return today
    if r == "tomorrow":
        return today + timedelta(days=1)
    if r == "day_after_tomorrow":
        return today + timedelta(days=2)
    if r == "next_week":
        return today + timedelta(days=7 - today.weekday())  # next Monday
    if r == "end_of_month":
        return end_of_month(today)
    if r == "next_month":
        return add_months(today, 1)
    m = re.fullmatch(r"(next|this)_(\w+)", r)
    if m and m.group(2) in WEEKDAYS:
        target = WEEKDAYS.index(m.group(2))
        delta = (target - today.weekday()) % 7
        if m.group(1) == "next" and delta == 0:
            delta = 7
        return today + timedelta(days=delta)
    m = re.fullmatch(r"in_(\d{1,3})_(day|days|week|weeks|month|months)", r)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit.startswith("day"):
            return today + timedelta(days=n)
        if unit.startswith("week"):
            return today + timedelta(weeks=n)
        return add_months(today, n)
    raise ValidationFailed("Unsupported relative date", code="invalid_date", details={"relative": relative})


def resolve_date(spec: dict, tz: str, now: datetime | None = None) -> date:
    today = today_in(tz, now)
    if spec.get("date"):
        try:
            return date.fromisoformat(spec["date"])
        except ValueError as e:
            raise ValidationFailed("Invalid date", code="invalid_date", details={"date": spec["date"]}) from e
    if spec.get("relative"):
        return resolve_relative_date(spec["relative"], today)
    raise ValidationFailed("Date is required", code="missing_date")


def resolve_datetime(spec: dict, tz: str, now: datetime | None = None, *, allow_past: bool = False) -> datetime:
    """Return an aware UTC datetime. Rejects past moments unless allow_past."""
    now = now or utcnow()
    d = resolve_date(spec, tz, now)
    t = _parse_time(spec.get("time")) or DEFAULT_TIME
    local = datetime.combine(d, t, tzinfo=ZoneInfo(tz))
    result = local.astimezone(UTC)
    if not allow_past and result <= now:
        raise ValidationFailed("That time is in the past", code="date_in_past",
                               details={"resolved": local.isoformat()})
    return result


def resolve_future_date(spec: dict, tz: str, now: datetime | None = None) -> date:
    d = resolve_date(spec, tz, now)
    if d < today_in(tz, now):
        raise ValidationFailed("That date is in the past", code="date_in_past", details={"resolved": d.isoformat()})
    return d
