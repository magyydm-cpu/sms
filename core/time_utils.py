"""Date/time helpers.

Storage convention:
* dates (debt date, due date, installment due date) -> ``YYYY-MM-DD`` strings.
* timestamps (created_at, paid_at, ...) -> UTC ISO-8601 ``YYYY-MM-DDTHH:MM:SSZ``.

Keeping timestamps in UTC makes the data independent from the device timezone;
the UI converts them to local time for display only.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

ISO_DATE = "%Y-%m-%d"
ISO_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().strftime(ISO_TIMESTAMP)


def iso_from_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime(ISO_TIMESTAMP)


def parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, ISO_TIMESTAMP).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def today() -> date:
    return date.today()


def today_iso() -> str:
    return today().isoformat()


def combine_date_and_now(date_value: date | None = None, now: datetime | None = None) -> str:
    """Build a UTC timestamp for a chosen local calendar date, using the current clock."""
    now = now or utc_now()
    chosen = date_value or now.astimezone().date()
    return iso_from_datetime(datetime.combine(chosen, now.timetz().replace(tzinfo=None), tzinfo=now.tzinfo))


def to_local(value: datetime) -> datetime:
    return value.astimezone()


def format_date_display(value) -> str:
    """Format a stored date (or date object) as dd/mm/yyyy."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    parsed = parse_date_safe(value)
    return parsed.strftime("%d/%m/%Y") if parsed else str(value)


def parse_date_safe(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], ISO_DATE).date()
    except ValueError:
        return None


def format_datetime_display(value: str | None) -> str:
    """Convert a stored UTC timestamp to the local timezone for display."""
    parsed = parse_iso(value)
    if not parsed:
        return value or ""
    local = parsed.astimezone()
    return local.strftime("%d/%m/%Y %H:%M")
