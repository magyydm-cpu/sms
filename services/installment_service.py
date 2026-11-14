"""Installment plan management."""
from __future__ import annotations

from datetime import date

from core import calculations, money, validation
from database.dao import (
    DebtDAO,
    InstallmentDAO,
    PaymentDAO,
    record_audit,
)
from database.db import Database
from database.models import InstallmentView
from services.errors import BusinessRuleError, NotFoundError

MIN_INSTALLMENTS = 2
MAX_INSTALLMENTS = 120


class InstallmentService:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_for_debt(self, debt_id: int, today: date | None = None) -> list[InstallmentView]:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            installments = InstallmentDAO(conn).list_by_debt(debt_id)
        return [
            InstallmentView(
                installment=item,
                currency=debt.currency,
                effective_status=calculations.installment_effective_status(
                    item.status, item.due_date, today=today
                ),
            )
            for item in installments
        ]

    def overdue_for_debt(self, debt_id: int, today: date | None = None) -> list[InstallmentView]:
        return [view for view in self.list_for_debt(debt_id, today=today) if view.is_overdue]

    def get(self, installment_id: int, today: date | None = None) -> InstallmentView:
        with self.db.transaction() as conn:
            installment = InstallmentDAO(conn).get(installment_id)
            if installment is None:
                raise NotFoundError("القسط")
            debt = DebtDAO(conn).get(installment.debt_id)
            if debt is None:
                raise NotFoundError("الدين")
        return InstallmentView(
            installment=installment,
            currency=debt.currency,
            effective_status=calculations.installment_effective_status(
                installment.status, installment.due_date, today=today
            ),
        )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def plan(
        self,
        debt_id: int,
        count,
        first_due_date,
        months_between=1,
        notes: str = "",
    ) -> list[InstallmentView]:
        count = validation.validate_positive_int(
            count, "count", minimum=MIN_INSTALLMENTS, maximum=MAX_INSTALLMENTS
        )
        months_between = validation.validate_interval_months(months_between)
        first_due = validation.parse_date(first_due_date, "first_due_date")
        notes = validation.validate_notes(notes)

        with self.db.transaction() as conn:
            debt_dao = DebtDAO(conn)
            debt = debt_dao.get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            if debt.status == calculations.STATUS_PAID:
                raise BusinessRuleError("لا يمكن إنشاء أقساط لدين مسدد بالكامل")
            installment_dao = InstallmentDAO(conn)
            if installment_dao.has_any(debt_id):
                raise BusinessRuleError("يوجد خطة أقساط سابقة لهذا الدين. احذفها أولاً.")
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
            remaining_minor = debt.amount_minor - paid_minor
            if remaining_minor <= 0:
                raise BusinessRuleError("لا يوجد مبلغ متبقٍ لتقسيمه")

            remaining = money.from_minor(remaining_minor, debt.currency)
            try:
                parts = calculations.split_amount(remaining, count, debt.currency)
            except ValueError:
                raise BusinessRuleError("المبلغ المتبقي صغير جداً لتقسيمه إلى هذا العدد من الأقساط") from None
            due_dates = calculations.installment_due_dates(first_due, count, months_between)

            rows = [
                {
                    "debt_id": debt_id,
                    "seq": index + 1,
                    "amount_minor": money.to_minor(part, debt.currency),
                    "due_date": due.isoformat(),
                    "notes": notes,
                }
                for index, (part, due) in enumerate(zip(parts, due_dates))
            ]
            installment_dao.insert_many(rows)
            debt_dao.update(debt_id, has_installments=1)
            record_audit(
                conn,
                "installment_plan",
                "create",
                debt_id,
                after={
                    "count": count,
                    "months_between": months_between,
                    "first_due_date": first_due.isoformat(),
                    "total_minor": sum(row["amount_minor"] for row in rows),
                    "currency": debt.currency,
                },
            )
        return self.list_for_debt(debt_id)

    def pay(self, installment_id: int, paid_at=None, notes: str = ""):
        # Imported lazily to keep the dependency direction one-way.
        from services.payment_service import PaymentService

        return PaymentService(self.db).pay_installment(installment_id, paid_at=paid_at, notes=notes)

    def delete_plan(self, debt_id: int) -> None:
        with self.db.transaction() as conn:
            debt_dao = DebtDAO(conn)
            if debt_dao.get(debt_id) is None:
                raise NotFoundError("الدين")
            installment_dao = InstallmentDAO(conn)
            installments = installment_dao.list_by_debt(debt_id)
            if not installments:
                raise BusinessRuleError("لا توجد خطة أقساط لحذفها")
            if any(item.status == calculations.INSTALLMENT_PAID for item in installments):
                raise BusinessRuleError("لا يمكن حذف خطة تحتوي أقساطاً مسددة")
            record_audit(
                conn,
                "installment_plan",
                "delete",
                debt_id,
                before={
                    "count": len(installments),
                    "installment_ids": [item.id for item in installments],
                },
            )
            installment_dao.delete_for_debt(debt_id)
            debt_dao.update(debt_id, has_installments=0)

    def is_fully_paid(self, debt_id: int) -> bool:
        with self.db.transaction() as conn:
            debt = DebtDAO(conn).get(debt_id)
            if debt is None:
                raise NotFoundError("الدين")
            paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
            return paid_minor >= debt.amount_minor
