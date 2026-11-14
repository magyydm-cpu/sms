from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core import calculations, money


def test_remaining_is_never_negative_and_exact():
    assert calculations.remaining(Decimal("100.00"), Decimal("30.10")) == Decimal("69.90")
    assert calculations.remaining(Decimal("100.00"), Decimal("100.00")) == Decimal("0")
    assert calculations.remaining(Decimal("100.00"), Decimal("120.00")) == Decimal("0")


def test_debt_status_transitions():
    assert calculations.debt_status(Decimal("100"), Decimal("0")) == "open"
    assert calculations.debt_status(Decimal("100"), Decimal("0.01")) == "partially_paid"
    assert calculations.debt_status(Decimal("100"), Decimal("100")) == "paid"


def test_group_totals_never_mixes_currencies():
    totals = calculations.group_totals(
        [
            ("USD", Decimal("100.00"), Decimal("40.00")),
            ("USD", Decimal("50.00"), Decimal("60.00")),
            ("IQD", Decimal("1000"), Decimal("0")),
        ]
    )
    assert totals["USD"]["total"] == Decimal("150.00")
    assert totals["USD"]["paid"] == Decimal("100.00")
    assert totals["USD"]["remaining"] == Decimal("50.00")
    assert totals["IQD"]["remaining"] == Decimal("1000")
    assert totals["USD"]["status"] == "partially_paid"


def test_split_amount_sums_exactly_usd():
    parts = calculations.split_amount(Decimal("100.00"), 3, "USD")
    assert sum(parts) == Decimal("100.00")
    assert parts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert all(part.as_tuple().exponent == -2 for part in parts)


def test_split_amount_sums_exactly_kwd():
    parts = calculations.split_amount(Decimal("100.000"), 3, "KWD")
    assert sum(parts) == Decimal("100.000")
    assert parts == [Decimal("33.334"), Decimal("33.333"), Decimal("33.333")]


def test_split_amount_iqd_integers():
    parts = calculations.split_amount(Decimal("1000"), 3, "IQD")
    assert sum(parts) == Decimal("1000")
    assert parts == [Decimal("334"), Decimal("333"), Decimal("333")]
    assert all(part == part.to_integral_value() for part in parts)


def test_split_amount_rejects_impossible_split():
    with pytest.raises(ValueError):
        calculations.split_amount(Decimal("0.01"), 3, "USD")


def test_add_months_clamps_month_end():
    assert calculations.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert calculations.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert calculations.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert calculations.add_months(date(2026, 3, 31), 12) == date(2027, 3, 31)


def test_installment_due_dates():
    dates = calculations.installment_due_dates(date(2026, 1, 31), 4, 1)
    assert dates == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_overdue_detection():
    assert calculations.is_overdue("2026-01-01", "pending", today=date(2026, 1, 2))
    assert not calculations.is_overdue("2026-01-01", "paid", today=date(2026, 1, 2))
    assert not calculations.is_overdue("2026-01-05", "pending", today=date(2026, 1, 2))
    assert (
        calculations.installment_effective_status("pending", "2026-01-01", today=date(2026, 1, 2))
        == "overdue"
    )
    assert (
        calculations.installment_effective_status("paid", "2026-01-01", today=date(2026, 1, 2))
        == "paid"
    )


def test_progress_percent():
    assert calculations.progress_percent(Decimal("100"), Decimal("25")) == 25.0
    assert calculations.progress_percent(Decimal("100"), Decimal("150")) == 100.0
    assert calculations.progress_percent(Decimal("0"), Decimal("10")) == 0.0
