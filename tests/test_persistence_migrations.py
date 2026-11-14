from __future__ import annotations

from decimal import Decimal

from database.db import Database, integrity_check
from database.migrations import LATEST_VERSION, apply_migrations, schema_version
from services import Services

REQUIRED_TABLES = {
    "debtors",
    "debts",
    "payments",
    "installments",
    "message_templates",
    "message_queue",
    "message_logs",
    "schedules",
    "currencies",
    "exchange_rates",
    "app_settings",
    "audit_logs",
    "sequences",
    "schema_migrations",
}


def test_all_required_tables_exist(db):
    rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row["name"] for row in rows}
    missing = REQUIRED_TABLES - names
    assert not missing, f"missing tables: {missing}"


def test_foreign_keys_enabled(db):
    assert db.query_one("PRAGMA foreign_keys")[0] == 1


def test_key_indexes_exist(db):
    rows = db.query("SELECT name FROM sqlite_master WHERE type='index'")
    names = {row["name"] for row in rows}
    for expected in (
        "ux_debtors_phone_key",
        "ix_debts_debtor",
        "ix_payments_debt",
        "ix_installments_debt_due",
        "ux_payments_receipt",
        "ix_audit_entity",
    ):
        assert expected in names


def test_migrations_are_idempotent(db):
    first = schema_version(db)
    apply_migrations(db)
    second = schema_version(db)
    assert first == second == LATEST_VERSION
    versions = [row["version"] for row in db.query("SELECT version FROM schema_migrations")]
    assert versions == [1, 2]


def test_seed_data_present(db):
    assert db.query_one("SELECT COUNT(*) FROM currencies")[0] >= 10
    assert db.query_one("SELECT COUNT(*) FROM app_settings")[0] >= 5
    assert db.query_one("SELECT COUNT(*) FROM message_templates")[0] >= 3
    iqd = db.query_one("SELECT decimal_places FROM currencies WHERE code='IQD'")
    assert iqd["decimal_places"] == 0


def test_integrity_check(db):
    assert integrity_check(db) == "ok"


def test_data_survives_close_and_reopen(db_path):
    first = Database(db_path)
    apply_migrations(first)
    services = Services(first)
    debtor = services.debtors.create("مدين دائم", "07705555555")
    debt = services.debts.create(debtor.id, "300.00", "USD", "2026-01-01", "2026-04-01")
    services.payments.add(debt.id, "100.00", notes="دفعة قبل الإغلاق")
    plan = services.installments.plan(debt.id, 2, "2026-05-01")
    receipt = services.payments.list_for_debt(debt.id)[0].receipt_no
    first.close()

    second = Database(db_path)
    apply_migrations(second)  # must be a safe no-op on reopen
    services2 = Services(second)
    overview = services2.debtors.overview(debtor.id)
    assert overview.debtor.original_phone == "07705555555"
    assert overview.totals["USD"]["total"] == Decimal("300.00")
    assert overview.totals["USD"]["paid"] == Decimal("100.00")
    assert overview.totals["USD"]["remaining"] == Decimal("200.00")
    assert [payment.receipt_no for payment in services2.payments.list_for_debt(debt.id)] == [receipt]
    assert len(services2.installments.list_for_debt(debt.id)) == 2
    assert [view.amount for view in services2.installments.list_for_debt(debt.id)] == plan_amounts(plan)
    second.close()


def plan_amounts(views):
    return [view.amount for view in views]
