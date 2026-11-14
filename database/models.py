"""Domain models (frozen dataclasses) mapped from SQLite rows.

Amounts are exposed as ``Decimal`` properties while the raw integer minor-unit
value remains available for storage operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core import calculations, money
from core.time_utils import format_date_display, format_datetime_display


def _row_value(row: Any, key: str, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


@dataclass(frozen=True)
class Currency:
    code: str
    name_ar: str
    name_en: str
    symbol: str
    decimal_places: int
    is_active: int = 1

    @classmethod
    def from_row(cls, row) -> "Currency":
        return cls(
            code=row["code"],
            name_ar=row["name_ar"],
            name_en=row["name_en"],
            symbol=row["symbol"],
            decimal_places=int(row["decimal_places"]),
            is_active=int(_row_value(row, "is_active", 1)),
        )

    @property
    def label(self) -> str:
        return f"{self.code} - {self.name_ar}"


@dataclass(frozen=True)
class Debtor:
    id: int
    name: str
    original_phone: str
    display_phone: str
    phone_key: str
    notes: str
    created_at: str
    updated_at: str
    name_key: str = ""
    is_active: int = 1

    @classmethod
    def from_row(cls, row) -> "Debtor":
        return cls(
            id=int(row["id"]),
            name=row["name"],
            original_phone=row["original_phone"] or "",
            display_phone=row["display_phone"] or "",
            phone_key=row["phone_key"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            name_key=_row_value(row, "name_key", "") or "",
            is_active=int(_row_value(row, "is_active", 1)),
        )

    @property
    def phone(self) -> str:
        return self.display_phone or self.original_phone


@dataclass(frozen=True)
class Debt:
    id: int
    debtor_id: int
    amount_minor: int
    currency: str
    debt_date: str
    due_date: str | None
    status: str
    notes: str
    created_at: str
    updated_at: str
    closed_at: str | None = None
    has_installments: int = 0

    @classmethod
    def from_row(cls, row) -> "Debt":
        return cls(
            id=int(row["id"]),
            debtor_id=int(row["debtor_id"]),
            amount_minor=int(row["original_amount_minor"]),
            currency=row["currency"],
            debt_date=row["debt_date"],
            due_date=_row_value(row, "due_date"),
            status=row["status"],
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=_row_value(row, "closed_at"),
            has_installments=int(_row_value(row, "has_installments", 0) or 0),
        )

    @property
    def amount(self) -> Decimal:
        return money.from_minor(self.amount_minor, self.currency)

    @property
    def amount_display(self) -> str:
        return money.format_money(self.amount, self.currency)

    @property
    def status_label(self) -> str:
        return calculations.STATUS_LABELS.get(self.status, self.status)

    @property
    def debt_date_display(self) -> str:
        return format_date_display(self.debt_date)

    @property
    def due_date_display(self) -> str:
        return format_date_display(self.due_date)


@dataclass(frozen=True)
class Payment:
    id: int
    debt_id: int
    amount_minor: int
    currency: str
    paid_at: str
    receipt_no: str
    notes: str
    created_at: str
    installment_id: int | None = None

    @classmethod
    def from_row(cls, row) -> "Payment":
        return cls(
            id=int(row["id"]),
            debt_id=int(row["debt_id"]),
            amount_minor=int(row["amount_minor"]),
            currency=row["currency"],
            paid_at=row["paid_at"],
            receipt_no=row["receipt_no"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"],
            installment_id=_row_value(row, "installment_id"),
        )

    @property
    def amount(self) -> Decimal:
        return money.from_minor(self.amount_minor, self.currency)

    @property
    def amount_display(self) -> str:
        return money.format_money(self.amount, self.currency)

    @property
    def paid_at_display(self) -> str:
        return format_datetime_display(self.paid_at)


@dataclass(frozen=True)
class Installment:
    id: int
    debt_id: int
    seq: int
    amount_minor: int
    due_date: str
    status: str
    notes: str
    created_at: str
    updated_at: str
    paid_at: str | None = None
    payment_id: int | None = None

    @classmethod
    def from_row(cls, row) -> "Installment":
        return cls(
            id=int(row["id"]),
            debt_id=int(row["debt_id"]),
            seq=int(row["seq"]),
            amount_minor=int(row["amount_minor"]),
            due_date=row["due_date"],
            status=row["status"],
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            paid_at=_row_value(row, "paid_at"),
            payment_id=_row_value(row, "payment_id"),
        )

    @property
    def due_date_display(self) -> str:
        return format_date_display(self.due_date)


@dataclass
class DebtSummary:
    debt: Debt
    total: Decimal
    paid: Decimal
    remaining: Decimal
    status: str
    installments_total: int = 0
    installments_paid: int = 0
    installments_overdue: int = 0

    @property
    def progress(self) -> float:
        return calculations.progress_percent(self.total, self.paid)

    @property
    def status_label(self) -> str:
        return calculations.STATUS_LABELS.get(self.status, self.status)

    @property
    def is_paid(self) -> bool:
        return self.status == calculations.STATUS_PAID


@dataclass
class DebtorSummary:
    debtor: Debtor
    debts: list[DebtSummary] = field(default_factory=list)
    totals: dict[str, dict] = field(default_factory=dict)

    @property
    def debt_count(self) -> int:
        return len(self.debts)

    @property
    def open_debt_count(self) -> int:
        return sum(1 for debt in self.debts if debt.status != calculations.STATUS_PAID)

    @property
    def remaining_by_currency(self) -> dict[str, Decimal]:
        """Remaining amount per currency - currencies are never added together."""
        return {
            currency: bucket["remaining"] for currency, bucket in self.totals.items()
        }

    def remaining_for(self, currency: str) -> Decimal:
        bucket = self.totals.get(currency)
        return bucket["remaining"] if bucket else Decimal("0")


@dataclass
class InstallmentView:
    installment: Installment
    currency: str
    effective_status: str

    @property
    def amount(self) -> Decimal:
        return money.from_minor(self.installment.amount_minor, self.currency)

    @property
    def amount_display(self) -> str:
        return money.format_money(self.amount, self.currency)

    @property
    def status_label(self) -> str:
        return calculations.INSTALLMENT_STATUS_LABELS.get(self.effective_status, self.effective_status)

    @property
    def is_overdue(self) -> bool:
        return self.effective_status == calculations.INSTALLMENT_OVERDUE

    @property
    def is_payable(self) -> bool:
        return self.effective_status in (
            calculations.INSTALLMENT_PENDING,
            calculations.INSTALLMENT_OVERDUE,
        )
