"""Financial calculations - Decimal only, no floats.

This module is deliberately UI-free and database-free so it can be unit tested
in isolation.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from . import money
from .time_utils import parse_date_safe

ZERO = Decimal("0")

STATUS_OPEN = "open"
STATUS_PARTIALLY_PAID = "partially_paid"
STATUS_PAID = "paid"
STATUS_CANCELLED = "cancelled"

INSTALLMENT_PENDING = "pending"
INSTALLMENT_PAID = "paid"
INSTALLMENT_OVERDUE = "overdue"
INSTALLMENT_CANCELLED = "cancelled"

STATUS_LABELS = {
    STATUS_OPEN: "غير مسدد",
    STATUS_PARTIALLY_PAID: "مسدد جزئياً",
    STATUS_PAID: "مسدد بالكامل",
    STATUS_CANCELLED: "ملغى",
}

INSTALLMENT_STATUS_LABELS = {
    INSTALLMENT_PENDING: "قيد الانتظار",
    INSTALLMENT_PAID: "مسدد",
    INSTALLMENT_OVERDUE: "متأخر",
    INSTALLMENT_CANCELLED: "ملغى",
}


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def remaining(total, paid) -> Decimal:
    """Amount still owed; never negative."""
    rest = _dec(total) - _dec(paid)
    return rest if rest > ZERO else ZERO


def debt_status(total, paid) -> str:
    total = _dec(total)
    paid = _dec(paid)
    if total > ZERO and paid >= total:
        return STATUS_PAID
    if paid > ZERO:
        return STATUS_PARTIALLY_PAID
    return STATUS_OPEN


def summarize(total, paid) -> dict:
    total = _dec(total)
    paid = _dec(paid)
    return {
        "total": total,
        "paid": paid,
        "remaining": remaining(total, paid),
        "status": debt_status(total, paid),
    }


def group_totals(entries: Iterable[tuple[str, Decimal, Decimal]]) -> dict[str, dict]:
    """Group ``(currency, total, paid)`` rows into per-currency summaries.

    Different currencies are never added together - that would require an
    exchange rate decision that does not belong in phase 2.
    """
    buckets: dict[str, dict] = {}
    for currency, total, paid in entries:
        bucket = buckets.setdefault(
            currency,
            {"currency": currency, "total": ZERO, "paid": ZERO, "remaining": ZERO, "status": STATUS_OPEN},
        )
        bucket["total"] += _dec(total)
        bucket["paid"] += _dec(paid)
    for bucket in buckets.values():
        bucket["remaining"] = remaining(bucket["total"], bucket["paid"])
        bucket["status"] = debt_status(bucket["total"], bucket["paid"])
    return buckets


def split_amount(amount, count: int, currency: str | None = None) -> list[Decimal]:
    """Split an amount into ``count`` parts that sum *exactly* to the original.

    The remainder (in minor units) is distributed one unit per earliest
    installment, so rounding can never create or destroy money.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    total_minor = money.to_minor(amount, currency)
    if total_minor <= 0:
        raise ValueError("amount must be positive")
    base, extra = divmod(total_minor, int(count))
    parts_minor = [base + 1] * extra + [base] * (int(count) - extra)
    if any(part <= 0 for part in parts_minor):
        raise ValueError("amount too small for this number of installments")
    return [money.from_minor(part, currency) for part in parts_minor]


def add_months(value: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's last day."""
    if not isinstance(value, date):
        parsed = parse_date_safe(value)
        if parsed is None:
            raise ValueError("invalid date")
        value = parsed
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def installment_due_dates(first_due: date, count: int, months_between: int = 1) -> list[date]:
    if count <= 0:
        return []
    months_between = max(1, int(months_between))
    return [add_months(first_due, index * months_between) for index in range(int(count))]


def _today(value: date | None = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date_safe(value)
    if parsed is None:
        raise ValueError("invalid date")
    return parsed


def is_overdue(due_date, status: str = INSTALLMENT_PENDING, today: date | None = None) -> bool:
    if status != INSTALLMENT_PENDING:
        return False
    due = _today(due_date)
    return due < _today(today)


def installment_effective_status(stored_status: str, due_date, today: date | None = None) -> str:
    """Combine the stored status with the due date (overdue is derived, not stored)."""
    if stored_status == INSTALLMENT_CANCELLED:
        return INSTALLMENT_CANCELLED
    if stored_status == INSTALLMENT_PAID:
        return INSTALLMENT_PAID
    if is_overdue(due_date, stored_status, today):
        return INSTALLMENT_OVERDUE
    return INSTALLMENT_PENDING


def count_overdue(installments: Iterable, today: date | None = None) -> int:
    total = 0
    for item in installments:
        status = getattr(item, "status", INSTALLMENT_PENDING)
        due = getattr(item, "due_date", None)
        if installment_effective_status(status, due, today) == INSTALLMENT_OVERDUE:
            total += 1
    return total


def progress_percent(total, paid) -> float:
    """UI progress only (0..100). Not used for financial math."""
    total = _dec(total)
    if total <= ZERO:
        return 0.0
    paid = _dec(paid)
    if paid > total:
        paid = total
    return float((paid / total) * Decimal(100))
