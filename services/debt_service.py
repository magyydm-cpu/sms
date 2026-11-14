"""Debt management."""
from __future__ import annotations

from datetime import date

from core import calculations, money, validation
from core.time_utils import today as today_date
from database.dao import (
    CurrencyDAO,
    DebtDAO,
    DebtorDAO,
    InstallmentDAO,
    PaymentDAO,
    record_audit,
    recalculate_debt_status,
)
from database.db import Database
from database.models import Debt, DebtSummary
from services.errors import BusinessRuleError, NotFoundError


class DebtService:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get(self, debt_id: int) -> Debt:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
        if debt is None:
            raise NotFoundError("الدين")
        return debt

    def overview(self, debt_id: int, today: date | None = None) -> DebtSummary:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            return self._build_summary(
                debt, PaymentDAO(conn), InstallmentDAO(conn), today=today
            )

    def list_for_debtor(self, debtor_id: int, today: date | None = None) -> list[DebtSummary]:
        with self.db.transaction() as conn:
            if DebtorDAO(conn).get(debtor_id) is None:
                raise NotFoundError("المدين")
            debts = DebtDAO(conn).list_by_debtor(debtor_id)
            payment_dao = PaymentDAO(conn)
            installment_dao = InstallmentDAO(conn)
            return [
                self._build_summary(debt, payment_dao, installment_dao, today=today)
                for debt in debts
            ]

    def debtor_total_remaining(self, debtor_id: int) -> dict[str, object]:
        """Remaining amount grouped by currency for one debtor."""
        entries = []
        with self.db.transaction() as conn:
            debt_dao = DebtDAO(conn)
            payment_dao = PaymentDAO(conn)
            for debt in debt_dao.list_by_debtor(debtor_id):
                total = debt.amount
                paid = money.from_minor(payment_dao.total_paid_minor(debt.id), debt.currency)
                entries.append((debt.currency, total, paid))
        return calculations.group_totals(entries)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def create(
        self,
        debtor_id: int,
        amount,
        currency: str,
        debt_date=None,
        due_date=None,
        notes: str = "",
    ) -> Debt:
        with self.db.transaction() as conn:
            if DebtorDAO(conn).get(debtor_id) is None:
                raise NotFoundError("المدين")
            allowed = CurrencyDAO(conn).codes()
            currency = validation.validate_currency(currency, allowed)
            amount_value = validation.validate_amount(amount, currency)
            debt_date_value = (
                validation.parse_date(debt_date, "debt_date")
                if debt_date not in (None, "")
                else today_date()
            )
            due_date_value = (
                validation.parse_date(due_date, "due_date") if due_date not in (None, "") else None
            )
            validation.validate_due_date(debt_date_value, due_date_value)
            notes = validation.validate_notes(notes)
            debt_id = DebtDAO(conn).insert(
                debtor_id=debtor_id,
                amount_minor=money.to_minor(amount_value, currency),
                currency=currency,
                debt_date=debt_date_value.isoformat(),
                due_date=due_date_value.isoformat() if due_date_value else None,
                notes=notes,
            )
            record_audit(conn, "debt", "create", debt_id, after=DebtDAO(conn).get_row(debt_id))
            debt = DebtDAO(conn).get(debt_id)
        assert debt is not None
        return debt

    def update(
        self,
        debt_id: int,
        amount=None,
        currency: str | None = None,
        debt_date=None,
        due_date=None,
        notes: str | None = None,
    ) -> Debt:
        """Partial update; ``None`` keeps the current value, ``""`` clears due_date."""
        with self.db.transaction() as conn:
            debt_dao = DebtDAO(conn)
            current = debt_dao.get(debt_id)
            if current is None:
                raise NotFoundError("الدين")
            before = debt_dao.get_row(debt_id)
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)

            target_currency = (
                validation.validate_currency(currency, CurrencyDAO(conn).codes())
                if currency
                else current.currency
            )
            if target_currency != current.currency and paid_minor > 0:
                raise BusinessRuleError(
                    "لا يمكن تغيير عملة دين عليه دفعات مسجلة. احذف الدفعات أولاً أو أنشئ ديناً جديداً."
                )

            target_amount = (
                validation.validate_amount(amount, target_currency)
                if amount is not None
                else money.from_minor(current.amount_minor, current.currency)
            )
            target_minor = money.to_minor(target_amount, target_currency)
            if target_minor < paid_minor:
                raise BusinessRuleError("لا يمكن أن يكون مبلغ الدين أقل من مجموع الدفعات المسجلة")

            target_debt_date = (
                validation.parse_date(debt_date, "debt_date")
                if debt_date not in (None, "")
                else validation.parse_date(current.debt_date)
            )
            if due_date is None:
                target_due = current.due_date
            elif due_date == "":
                target_due = None
            else:
                target_due = validation.parse_date(due_date, "due_date").isoformat()
            validation.validate_due_date(
                target_debt_date,
                validation.parse_date(target_due) if target_due else None,
            )

            has_plan = InstallmentDAO(conn).has_any(debt_id)
            if has_plan and target_minor != current.amount_minor:
                raise BusinessRuleError(
                    "لا يمكن تعديل مبلغ دين له خطة أقساط. احذف الخطة أولاً ثم عدّل المبلغ."
                )
            if has_plan and target_currency != current.currency:
                # Installments do not store a currency; reinterpreting their minor
                # units under another currency would silently change their value.
                raise BusinessRuleError(
                    "لا يمكن تغيير عملة دين له خطة أقساط. احذف الخطة أولاً."
                )

            debt_dao.update(
                debt_id,
                original_amount_minor=target_minor,
                currency=target_currency,
                debt_date=target_debt_date.isoformat(),
                due_date=target_due,
                notes=validation.validate_notes(notes) if notes is not None else current.notes,
            )
            recalculate_debt_status(conn, debt_id)
            record_audit(
                conn, "debt", "update", debt_id, before=before, after=debt_dao.get_row(debt_id)
            )
            updated = debt_dao.get(debt_id)
        assert updated is not None
        return updated

    def delete(self, debt_id: int) -> None:
        with self.db.transaction() as conn:
            debt_dao = DebtDAO(conn)
            snapshot = debt_dao.get_row(debt_id)
            if snapshot is None:
                raise NotFoundError("الدين")
            snapshot["payments"] = [dict(row) for row in conn.execute(
                "SELECT id, amount_minor, paid_at, receipt_no FROM payments WHERE debt_id = ?",
                (int(debt_id),),
            ).fetchall()]
            snapshot["installments"] = [dict(row) for row in conn.execute(
                "SELECT id, seq, amount_minor, due_date, status FROM installments WHERE debt_id = ?",
                (int(debt_id),),
            ).fetchall()]
            record_audit(conn, "debt", "delete", debt_id, before=snapshot)
            debt_dao.delete(debt_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _build_summary(
        debt: Debt,
        payment_dao: PaymentDAO,
        installment_dao: InstallmentDAO,
        today: date | None = None,
    ) -> DebtSummary:
        total = debt.amount
        paid = money.from_minor(payment_dao.total_paid_minor(debt.id), debt.currency)
        info = calculations.summarize(total, paid)
        installments = installment_dao.list_by_debt(debt.id)
        return DebtSummary(
            debt=debt,
            total=info["total"],
            paid=info["paid"],
            remaining=info["remaining"],
            status=info["status"],
            installments_total=len(installments),
            installments_paid=sum(1 for item in installments if item.status == "paid"),
            installments_overdue=calculations.count_overdue(installments, today=today),
        )
