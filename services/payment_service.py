"""Payment management."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from core import calculations, money, validation
from core.time_utils import (
    combine_date_and_now,
    iso_from_datetime,
    iso_now,
    parse_iso,
)
from database.dao import (
    DebtDAO,
    InstallmentDAO,
    PaymentDAO,
    SequenceDAO,
    record_audit,
    recalculate_debt_status,
)
from database.db import Database
from database.models import Payment
from services.errors import BusinessRuleError, NotFoundError


class PaymentService:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_for_debt(self, debt_id: int) -> list[Payment]:
        with self.db.transaction() as conn:
            if DebtDAO(conn).get(debt_id) is None:
                raise NotFoundError("الدين")
            return PaymentDAO(conn).list_by_debt(debt_id)

    def get(self, payment_id: int) -> Payment:
        with self.db.transaction() as conn:
            payment = PaymentDAO(conn).get(payment_id)
        if payment is None:
            raise NotFoundError("الدفعة")
        return payment

    def total_paid(self, debt_id: int) -> Decimal:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
            return money.from_minor(paid_minor, debt.currency)

    def remaining(self, debt_id: int) -> Decimal:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
            return money.from_minor(max(0, debt.amount_minor - paid_minor), debt.currency)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def add(
        self,
        debt_id: int,
        amount,
        paid_at=None,
        notes: str = "",
        receipt_no: str | None = None,
    ) -> Payment:
        notes = validation.validate_notes(notes)
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            amount_value = validation.validate_amount(amount, debt.currency)
            amount_minor = money.to_minor(amount_value, debt.currency)
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
            remaining_minor = max(0, debt.amount_minor - paid_minor)
            if remaining_minor <= 0:
                raise BusinessRuleError("هذا الدين مسدد بالكامل")
            if amount_minor > remaining_minor:
                raise BusinessRuleError(
                    f"المبلغ أكبر من المتبقي "
                    f"({money.format_money(money.from_minor(remaining_minor, debt.currency), debt.currency)})"
                )
            receipt = validation.validate_receipt_no(receipt_no) or self._next_receipt_no(conn)
            timestamp = self._normalize_paid_at(paid_at)
            try:
                payment_id = PaymentDAO(conn).insert(
                    debt_id=debt_id,
                    amount_minor=amount_minor,
                    currency=debt.currency,
                    paid_at=timestamp,
                    receipt_no=receipt,
                    notes=notes,
                )
            except sqlite3.IntegrityError as exc:
                if "receipt" in str(exc).lower() or "unique" in str(exc).lower():
                    raise BusinessRuleError("رقم الإيصال مستخدم مسبقاً") from None
                if "payment_exceeds_debt" in str(exc):
                    raise BusinessRuleError("المبلغ أكبر من المتبقي على الدين") from None
                raise
            created = PaymentDAO(conn).get(payment_id)
            record_audit(
                conn,
                "payment",
                "create",
                payment_id,
                after=dict(created.__dict__) if created else None,
            )
            recalculate_debt_status(conn, debt_id)
            payment = PaymentDAO(conn).get(payment_id)
        assert payment is not None
        return payment

    def pay_installment(self, installment_id: int, paid_at=None, notes: str = "") -> Payment:
        notes = validation.validate_notes(notes)
        with self.db.transaction() as conn:
            installment_dao = InstallmentDAO(conn)
            installment = installment_dao.get(installment_id)
            if installment is None:
                raise NotFoundError("القسط")
            if installment.status != calculations.INSTALLMENT_PENDING:
                raise BusinessRuleError("هذا القسط غير قابل للدفع (مسدد أو ملغى)")
            debt = DebtDAO(conn).get(installment.debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            payment_dao = PaymentDAO(conn)
            paid_minor = payment_dao.total_paid_minor(debt.id)
            remaining_minor = max(0, debt.amount_minor - paid_minor)
            if installment.amount_minor > remaining_minor:
                raise BusinessRuleError(
                    "المبلغ المتبقي على الدين أقل من قيمة القسط. سجّل دفعة جزئية بدلاً من ذلك."
                )
            receipt = self._next_receipt_no(conn)
            timestamp = self._normalize_paid_at(paid_at)
            try:
                payment_id = payment_dao.insert(
                    debt_id=debt.id,
                    amount_minor=installment.amount_minor,
                    currency=debt.currency,
                    paid_at=timestamp,
                    receipt_no=receipt,
                    notes=notes,
                    installment_id=installment.id,
                )
            except sqlite3.IntegrityError as exc:
                if "payment_exceeds_debt" in str(exc):
                    raise BusinessRuleError("المبلغ أكبر من المتبقي على الدين") from None
                raise
            installment_dao.mark_paid(installment.id, timestamp, payment_id)
            record_audit(
                conn,
                "installment",
                "pay",
                installment.id,
                before={"status": installment.status},
                after={"status": "paid", "payment_id": payment_id},
            )
            recalculate_debt_status(conn, debt.id)
            payment = payment_dao.get(payment_id)
        assert payment is not None
        return payment

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _next_receipt_no(conn: sqlite3.Connection) -> str:
        number = SequenceDAO(conn).next("receipt")
        year = datetime.now().strftime("%y")
        return f"R-{year}-{number:05d}"

    @staticmethod
    def _normalize_paid_at(value) -> str:
        if value in (None, ""):
            return iso_now()
        if isinstance(value, datetime):
            return iso_from_datetime(value)
        if isinstance(value, date):
            return combine_date_and_now(value)
        text = str(value).strip()
        parsed_timestamp = parse_iso(text)
        if parsed_timestamp is not None:
            return iso_from_datetime(parsed_timestamp)
        # A plain date (YYYY-MM-DD / dd/mm/yyyy) plus the current clock.
        return combine_date_and_now(validation.parse_date(text, "paid_at"))
