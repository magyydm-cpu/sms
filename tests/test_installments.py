from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from services.errors import BusinessRuleError


class TestInstallmentPlan:
    def test_plan_splits_remaining_exactly(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD", "2026-01-01")
        services.payments.add(debt.id, "10.00")
        views = services.installments.plan(debt.id, 4, "2026-02-01")
        assert len(views) == 4
        assert [view.amount for view in views] == [
            Decimal("22.50"),
            Decimal("22.50"),
            Decimal("22.50"),
            Decimal("22.50"),
        ]
        assert [view.installment.due_date for view in views] == [
            "2026-02-01",
            "2026-03-01",
            "2026-04-01",
            "2026-05-01",
        ]
        # The schedule never exceeds the debt's remaining amount.
        assert sum(view.amount for view in views) == Decimal("90.00")
        assert services.debts.get(debt.id).has_installments == 1

    def test_split_with_remainder(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 3, "2026-02-01")
        assert [view.amount for view in views] == [
            Decimal("33.34"),
            Decimal("33.33"),
            Decimal("33.33"),
        ]
        assert sum(view.amount for view in views) == Decimal("100.00")

    def test_due_dates_respect_month_end(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 3, "2026-01-31", months_between=1)
        assert [view.installment.due_date for view in views] == [
            "2026-01-31",
            "2026-02-28",
            "2026-03-31",
        ]

    def test_cannot_plan_twice(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.installments.plan(debt.id, 2, "2026-02-01")
        with pytest.raises(BusinessRuleError):
            services.installments.plan(debt.id, 2, "2026-03-01")

    def test_plan_validation(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        with pytest.raises(Exception):
            services.installments.plan(debt.id, 1, "2026-02-01")
        with pytest.raises(Exception):
            services.installments.plan(debt.id, 3, "bad-date")

    def test_cannot_plan_paid_debt(self, services, debtor):
        debt = services.debts.create(debtor.id, "10.00", "USD")
        services.payments.add(debt.id, "10.00")
        with pytest.raises(BusinessRuleError):
            services.installments.plan(debt.id, 2, "2026-02-01")

    def test_database_trigger_blocks_schedule_above_debt(self, services, db, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.installments.plan(debt.id, 2, "2026-02-01")
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO installments(debt_id, seq, amount_minor, due_date, status, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', 'now', 'now')",
                    (debt.id, 99, 900000, "2026-05-01"),
                )


class TestInstallmentStatus:
    def test_overdue_is_derived_from_due_date(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 3, "2026-01-01", months_between=1)
        later = date(2026, 2, 15)
        refreshed = services.installments.list_for_debt(debt.id, today=later)
        assert [view.effective_status for view in refreshed] == [
            "overdue",
            "overdue",
            "pending",
        ]
        assert [view.status_label for view in refreshed] == ["متأخر", "متأخر", "قيد الانتظار"]
        assert len(services.installments.overdue_for_debt(debt.id, today=later)) == 2
        # Stored status stays "pending": overdue is not persisted.
        assert all(view.installment.status == "pending" for view in views)

    def test_debt_summary_counts_overdue(self, services, debtor):
        debt = services.debts.create(debtor.id, "90.00", "USD")
        services.installments.plan(debt.id, 3, "2020-01-01")
        summary = services.debts.overview(debt.id, today=date(2026, 1, 1))
        assert summary.installments_total == 3
        assert summary.installments_overdue == 3


class TestInstallmentPayment:
    def test_paying_installment_records_payment_and_updates_balance(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 2, "2026-02-01")
        installment = views[0].installment

        payment = services.installments.pay(installment.id)
        assert payment.amount == Decimal("50.00")
        assert payment.installment_id == installment.id
        assert payment.receipt_no.startswith("R-")

        summary = services.debts.overview(debt.id)
        assert summary.paid == Decimal("50.00")
        assert summary.remaining == Decimal("50.00")
        assert summary.status == "partially_paid"

        refreshed = services.installments.get(installment.id)
        assert refreshed.installment.status == "paid"
        assert refreshed.installment.paid_at is not None
        assert refreshed.installment.payment_id == payment.id

    def test_paying_last_installment_settles_debt(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 2, "2026-02-01")
        for view in views:
            services.installments.pay(view.installment.id)
        summary = services.debts.overview(debt.id)
        assert summary.status == "paid"
        assert summary.remaining == Decimal("0")
        assert services.installments.overdue_for_debt(debt.id) == []

    def test_cannot_pay_installment_twice(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 2, "2026-02-01")
        services.installments.pay(views[0].installment.id)
        with pytest.raises(BusinessRuleError):
            services.installments.pay(views[0].installment.id)

    def test_full_manual_payment_cancels_pending_installments(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.installments.plan(debt.id, 4, "2026-02-01")
        services.payments.add(debt.id, "100.00")
        views = services.installments.list_for_debt(debt.id)
        assert all(view.installment.status == "cancelled" for view in views)
        assert services.debts.overview(debt.id).status == "paid"

    def test_delete_plan_only_when_no_paid_installments(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        views = services.installments.plan(debt.id, 2, "2026-02-01")
        services.installments.pay(views[0].installment.id)
        with pytest.raises(BusinessRuleError):
            services.installments.delete_plan(debt.id)

        other = services.debts.create(debtor.id, "50.00", "USD")
        services.installments.plan(other.id, 2, "2026-02-01")
        services.installments.delete_plan(other.id)
        assert services.installments.list_for_debt(other.id) == []
        assert services.debts.get(other.id).has_installments == 0
