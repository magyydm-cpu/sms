from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.errors import BusinessRuleError, NotFoundError


class TestDebts:
    def test_multiple_debts_for_one_debtor(self, services, debtor):
        services.debts.create(debtor.id, "100.00", "USD", "2026-01-01", "2026-02-01")
        services.debts.create(debtor.id, "250000", "IQD", "2026-01-05")
        overview = services.debtors.overview(debtor.id)
        assert overview.debt_count == 2
        assert overview.totals["USD"]["total"] == Decimal("100.00")
        assert overview.totals["IQD"]["total"] == Decimal("250000")
        # Currencies are reported separately, never summed together.
        assert set(overview.totals) == {"USD", "IQD"}

    def test_debt_fields_and_defaults(self, services, debtor):
        debt = services.debts.create(debtor.id, "75.5", "usd", notes="دين تجريبي")
        assert debt.currency == "USD"
        assert debt.amount == Decimal("75.50")
        assert debt.status == "open"
        assert debt.due_date is None
        assert debt.notes == "دين تجريبي"

    def test_unknown_currency_rejected(self, services, debtor):
        with pytest.raises(Exception):
            services.debts.create(debtor.id, "10", "XYZ")

    def test_due_date_before_debt_date_rejected(self, services, debtor):
        with pytest.raises(Exception):
            services.debts.create(
                debtor.id, "10", "USD", debt_date="2026-02-01", due_date="2026-01-01"
            )

    def test_update_due_date_and_clear_it(self, services, debtor):
        debt = services.debts.create(debtor.id, "10", "USD", "2026-01-01", "2026-02-01")
        updated = services.debts.update(debt.id, due_date="")
        assert updated.due_date is None
        updated = services.debts.update(debt.id, due_date="2026-03-01")
        assert updated.due_date == "2026-03-01"

    def test_cannot_lower_amount_below_paid(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "60.00")
        with pytest.raises(BusinessRuleError):
            services.debts.update(debt.id, amount="50.00")
        updated = services.debts.update(debt.id, amount="80.00")
        assert updated.amount == Decimal("80.00")

    def test_cannot_change_currency_when_payments_exist(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "10.00")
        with pytest.raises(BusinessRuleError):
            services.debts.update(debt.id, currency="EUR")

    def test_cannot_change_currency_or_amount_when_plan_exists(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.installments.plan(debt.id, 2, "2026-02-01")
        with pytest.raises(BusinessRuleError):
            services.debts.update(debt.id, currency="EUR")
        with pytest.raises(BusinessRuleError):
            services.debts.update(debt.id, amount="120.00")
        # Non-financial edits are still allowed.
        assert services.debts.update(debt.id, notes="ملاحظة").notes == "ملاحظة"

    def test_delete_debt_cascades(self, services, db, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "10.00")
        services.debts.delete(debt.id)
        assert db.query_one("SELECT COUNT(*) FROM debts")[0] == 0
        assert db.query_one("SELECT COUNT(*) FROM payments")[0] == 0
        with pytest.raises(NotFoundError):
            services.debts.get(debt.id)


class TestPayments:
    def test_partial_then_full_payment_updates_status(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        payment = services.payments.add(debt.id, "40.50", notes="دفعة أولى")
        assert payment.amount == Decimal("40.50")
        summary = services.debts.overview(debt.id)
        assert summary.paid == Decimal("40.50")
        assert summary.remaining == Decimal("59.50")
        assert summary.status == "partially_paid"

        services.payments.add(debt.id, "59.50")
        summary = services.debts.overview(debt.id)
        assert summary.remaining == Decimal("0")
        assert summary.status == "paid"
        assert services.debts.get(debt.id).closed_at is not None

    def test_arabic_amount_input(self, services, debtor):
        debt = services.debts.create(debtor.id, "200.00", "USD")
        payment = services.payments.add(debt.id, "١٠٠٫٢٥")
        assert payment.amount == Decimal("100.25")

    def test_kwd_three_decimals(self, services, debtor):
        debt = services.debts.create(debtor.id, "10.000", "KWD")
        services.payments.add(debt.id, "3.333")
        services.payments.add(debt.id, "6.667")
        summary = services.debts.overview(debt.id)
        assert summary.paid == Decimal("10.000")
        assert summary.remaining == Decimal("0")
        assert summary.status == "paid"

    def test_overpayment_is_blocked(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "99.99")
        with pytest.raises(BusinessRuleError):
            services.payments.add(debt.id, "0.02")

    def test_payment_on_paid_debt_is_blocked(self, services, debtor):
        debt = services.debts.create(debtor.id, "10.00", "USD")
        services.payments.add(debt.id, "10.00")
        with pytest.raises(BusinessRuleError):
            services.payments.add(debt.id, "1.00")

    def test_database_trigger_blocks_direct_overpayment(self, services, db, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO payments(debt_id, amount_minor, currency, paid_at, receipt_no, "
                    "notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (debt.id, 15000, "USD", "2026-01-01T00:00:00Z", "DIRECT-1", "", "now"),
                )
        # The failed insert was rolled back.
        assert services.debts.overview(debt.id).paid == Decimal("0")

    def test_receipts_are_generated_and_unique(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        first = services.payments.add(debt.id, "10.00")
        second = services.payments.add(debt.id, "10.00")
        assert first.receipt_no.startswith("R-")
        assert first.receipt_no != second.receipt_no

    def test_custom_duplicate_receipt_rejected(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "10.00", receipt_no="MANUAL-1")
        with pytest.raises(BusinessRuleError):
            services.payments.add(debt.id, "10.00", receipt_no="MANUAL-1")

    def test_paid_at_timestamp_stored_as_utc(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        moment = datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc)
        payment = services.payments.add(debt.id, "10.00", paid_at=moment)
        assert payment.paid_at == "2026-01-15T12:30:00Z"

    def test_payment_history_is_complete_and_newest_first(self, services, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "10.00", paid_at="2026-01-01", notes="قديمة")
        services.payments.add(debt.id, "20.00", paid_at="2026-02-01", notes="جديدة")
        history = services.payments.list_for_debt(debt.id)
        assert [payment.amount for payment in history] == [Decimal("20.00"), Decimal("10.00")]
        assert history[0].notes == "جديدة"

    def test_debtor_totals_include_payments(self, services, debtor):
        usd = services.debts.create(debtor.id, "100.00", "USD")
        iqd = services.debts.create(debtor.id, "50000", "IQD")
        services.payments.add(usd.id, "25.00")
        services.payments.add(iqd.id, "20000")
        overview = services.debtors.overview(debtor.id)
        assert overview.totals["USD"]["remaining"] == Decimal("75.00")
        assert overview.totals["IQD"]["remaining"] == Decimal("30000")
        # Per-currency only: no cross-currency addition anywhere.
        assert overview.remaining_by_currency == {
            "USD": Decimal("75.00"),
            "IQD": Decimal("30000"),
        }
        assert overview.open_debt_count == 2

    def test_audit_log_contains_payment(self, services, db, debtor):
        debt = services.debts.create(debtor.id, "100.00", "USD")
        payment = services.payments.add(debt.id, "10.00")
        row = db.query_one(
            "SELECT * FROM audit_logs WHERE entity='payment' AND action='create' AND entity_id=?",
            (str(payment.id),),
        )
        assert row is not None
