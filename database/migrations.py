"""Schema migrations.

Migrations are ordered, and each runs inside a single transaction together with
the row that records it in ``schema_migrations``. Applying them twice is safe:
already-applied versions are skipped. New schema changes in later phases must
be added as a new ``(version, name, function)`` entry at the end of
``MIGRATIONS`` - never by editing an already shipped migration.
"""
from __future__ import annotations

import sqlite3

from core.time_utils import iso_now
from database.db import Database

LATEST_VERSION = 2

SCHEMA_V1: tuple[str, ...] = (
    # ------------------------------------------------------------------
    # debtors
    # ------------------------------------------------------------------
    """
    CREATE TABLE debtors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        name_key TEXT NOT NULL DEFAULT '',
        original_phone TEXT NOT NULL DEFAULT '',
        display_phone TEXT NOT NULL DEFAULT '',
        phone_key TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # Phone uniqueness is enforced on the *cleaned* key, so "+964 770 123 4567"
    # and "00964-770-123-4567" cannot both be saved. Empty phones are allowed by
    # the schema but rejected by the service/UI layer in this phase.
    "CREATE UNIQUE INDEX ux_debtors_phone_key ON debtors(phone_key) WHERE phone_key <> ''",
    "CREATE INDEX ix_debtors_name_key ON debtors(name_key)",
    "CREATE INDEX ix_debtors_active ON debtors(is_active)",
    # ------------------------------------------------------------------
    # currencies
    # ------------------------------------------------------------------
    """
    CREATE TABLE currencies (
        code TEXT PRIMARY KEY,
        name_ar TEXT NOT NULL,
        name_en TEXT NOT NULL,
        symbol TEXT NOT NULL,
        decimal_places INTEGER NOT NULL DEFAULT 2 CHECK (decimal_places BETWEEN 0 AND 4),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
    )
    """,
    # ------------------------------------------------------------------
    # debts
    # ------------------------------------------------------------------
    """
    CREATE TABLE debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debtor_id INTEGER NOT NULL REFERENCES debtors(id) ON DELETE CASCADE,
        original_amount_minor INTEGER NOT NULL CHECK (original_amount_minor > 0),
        currency TEXT NOT NULL REFERENCES currencies(code),
        debt_date TEXT NOT NULL,
        due_date TEXT,
        status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'partially_paid', 'paid', 'cancelled')),
        has_installments INTEGER NOT NULL DEFAULT 0 CHECK (has_installments IN (0, 1)),
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        closed_at TEXT
    )
    """,
    "CREATE INDEX ix_debts_debtor ON debts(debtor_id)",
    "CREATE INDEX ix_debts_status ON debts(status)",
    "CREATE INDEX ix_debts_due_date ON debts(due_date)",
    # ------------------------------------------------------------------
    # payments
    # ------------------------------------------------------------------
    """
    CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
        installment_id INTEGER REFERENCES installments(id) ON DELETE SET NULL,
        amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
        currency TEXT NOT NULL REFERENCES currencies(code),
        paid_at TEXT NOT NULL,
        receipt_no TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX ux_payments_receipt ON payments(receipt_no)",
    "CREATE INDEX ix_payments_debt ON payments(debt_id, paid_at)",
    "CREATE INDEX ix_payments_paid_at ON payments(paid_at)",
    # One payment can settle at most one installment.
    "CREATE UNIQUE INDEX ux_payments_installment ON payments(installment_id) WHERE installment_id IS NOT NULL",
    # ------------------------------------------------------------------
    # installments
    # ------------------------------------------------------------------
    """
    CREATE TABLE installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL CHECK (seq > 0),
        amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'paid', 'cancelled')),
        paid_at TEXT,
        payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (debt_id, seq)
    )
    """,
    "CREATE INDEX ix_installments_debt_due ON installments(debt_id, due_date)",
    "CREATE INDEX ix_installments_status ON installments(status)",
    "CREATE UNIQUE INDEX ux_installments_payment ON installments(payment_id) WHERE payment_id IS NOT NULL",
    # ------------------------------------------------------------------
    # Database-level financial guards (defence in depth next to the services)
    # ------------------------------------------------------------------
    """
    CREATE TRIGGER trg_payments_guard_insert
    BEFORE INSERT ON payments
    BEGIN
        SELECT CASE
            WHEN NEW.amount_minor <= 0 THEN RAISE(ABORT, 'payment_amount_must_be_positive')
            WHEN NEW.amount_minor + (
                    SELECT COALESCE(SUM(amount_minor), 0) FROM payments WHERE debt_id = NEW.debt_id
                 ) > (SELECT original_amount_minor FROM debts WHERE id = NEW.debt_id)
                THEN RAISE(ABORT, 'payment_exceeds_debt')
            WHEN NEW.installment_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM installments
                    WHERE id = NEW.installment_id AND debt_id = NEW.debt_id AND status = 'pending'
                 )
                THEN RAISE(ABORT, 'invalid_installment_reference')
        END;
    END
    """,
    """
    CREATE TRIGGER trg_payments_guard_update
    BEFORE UPDATE OF amount_minor, debt_id ON payments
    BEGIN
        SELECT CASE
            WHEN NEW.amount_minor <= 0 THEN RAISE(ABORT, 'payment_amount_must_be_positive')
            WHEN NEW.amount_minor + (
                    SELECT COALESCE(SUM(amount_minor), 0) FROM payments
                    WHERE debt_id = NEW.debt_id AND id <> NEW.id
                 ) > (SELECT original_amount_minor FROM debts WHERE id = NEW.debt_id)
                THEN RAISE(ABORT, 'payment_exceeds_debt')
        END;
    END
    """,
    """
    CREATE TRIGGER trg_installments_guard_insert
    BEFORE INSERT ON installments
    BEGIN
        SELECT CASE
            WHEN NEW.amount_minor <= 0 THEN RAISE(ABORT, 'installment_amount_must_be_positive')
            WHEN NEW.amount_minor + (
                    SELECT COALESCE(SUM(amount_minor), 0) FROM installments
                    WHERE debt_id = NEW.debt_id AND status <> 'cancelled'
                 ) > (SELECT original_amount_minor FROM debts WHERE id = NEW.debt_id)
                THEN RAISE(ABORT, 'installments_exceed_debt')
        END;
    END
    """,
    # ------------------------------------------------------------------
    # Messaging / scheduling scaffolding (used from phase 3 onwards)
    # ------------------------------------------------------------------
    """
    CREATE TABLE message_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT 'sms' CHECK (channel IN ('sms', 'whatsapp', 'notification')),
        body TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX ux_message_templates_name_channel ON message_templates(name, channel)",
    """
    CREATE TABLE message_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debtor_id INTEGER REFERENCES debtors(id) ON DELETE CASCADE,
        debt_id INTEGER REFERENCES debts(id) ON DELETE CASCADE,
        installment_id INTEGER REFERENCES installments(id) ON DELETE SET NULL,
        template_id INTEGER REFERENCES message_templates(id) ON DELETE SET NULL,
        channel TEXT NOT NULL DEFAULT 'sms',
        phone_original TEXT NOT NULL DEFAULT '',
        phone_key TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
        scheduled_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        last_error TEXT,
        created_at TEXT NOT NULL,
        sent_at TEXT
    )
    """,
    "CREATE INDEX ix_message_queue_status_sched ON message_queue(status, scheduled_at)",
    "CREATE INDEX ix_message_queue_debtor ON message_queue(debtor_id)",
    """
    CREATE TABLE message_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER REFERENCES message_queue(id) ON DELETE CASCADE,
        channel TEXT NOT NULL DEFAULT 'sms',
        status TEXT NOT NULL,
        provider_message_id TEXT,
        error TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX ix_message_logs_queue ON message_logs(queue_id)",
    """
    CREATE TABLE schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'reminder'
            CHECK (kind IN ('reminder', 'backup', 'report', 'custom')),
        target TEXT NOT NULL DEFAULT 'all',
        time_of_day TEXT NOT NULL DEFAULT '09:00',
        days_of_week TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
        is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
        last_run_at TEXT,
        next_run_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE exchange_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_code TEXT NOT NULL REFERENCES currencies(code),
        quote_code TEXT NOT NULL REFERENCES currencies(code),
        rate TEXT NOT NULL,
        effective_date TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL,
        UNIQUE (base_code, quote_code, effective_date)
    )
    """,
    "CREATE INDEX ix_exchange_rates_date ON exchange_rates(effective_date)",
    """
    CREATE TABLE app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        value_type TEXT NOT NULL DEFAULT 'text'
            CHECK (value_type IN ('text', 'int', 'decimal', 'bool', 'json')),
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        entity_id TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL,
        actor TEXT NOT NULL DEFAULT 'local',
        before_json TEXT,
        after_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX ix_audit_entity ON audit_logs(entity, entity_id)",
    "CREATE INDEX ix_audit_created ON audit_logs(created_at)",
    """
    CREATE TABLE sequences (
        name TEXT PRIMARY KEY,
        value INTEGER NOT NULL DEFAULT 0
    )
    """,
)

CURRENCIES_V2 = (
    ("IQD", "دينار عراقي", "Iraqi Dinar", "د.ع", 0),
    ("USD", "دولار أمريكي", "US Dollar", "$", 2),
    ("EUR", "يورو", "Euro", "€", 2),
    ("GBP", "جنيه إسترليني", "British Pound", "£", 2),
    ("SAR", "ريال سعودي", "Saudi Riyal", "ر.س", 2),
    ("AED", "درهم إماراتي", "UAE Dirham", "د.إ", 2),
    ("KWD", "دينار كويتي", "Kuwaiti Dinar", "د.ك", 3),
    ("JOD", "دينار أردني", "Jordanian Dinar", "د.أ", 3),
    ("EGP", "جنيه مصري", "Egyptian Pound", "ج.م", 2),
    ("TRY", "ليرة تركية", "Turkish Lira", "₺", 2),
)

SETTINGS_V2 = (
    ("default_currency", "IQD", "text"),
    ("reminder_days_before_due", "3", "int"),
    ("reminder_time", "09:00", "text"),
    ("theme_style", "Light", "text"),
    ("app_language", "ar", "text"),
    ("backup_enabled", "0", "bool"),
)

TEMPLATES_V2 = (
    (
        "تذكير بموعد الدفع",
        "sms",
        "عزيزي {debtor_name}،\nنود تذكيركم بأن مبلغ {remaining} {currency} "
        "مستحق بتاريخ {due_date}.\nشكراً لتعاونكم.",
    ),
    (
        "تذكير بقسط متأخر",
        "sms",
        "عزيزي {debtor_name}،\nالقسط رقم {installment_seq} بمبلغ {amount} {currency} "
        "مستحق بتاريخ {due_date} ولم يتم سداده بعد.\nنرجو المبادرة بالسداد.",
    ),
    (
        "إشعار استلام دفعة",
        "sms",
        "عزيزي {debtor_name}،\nتم استلام دفعة بمبلغ {amount} {currency} بتاريخ {paid_at}.\n"
        "المبلغ المتبقي: {remaining} {currency}.\nشكراً لكم.",
    ),
)


def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_V1:
        conn.execute(statement)


def _migration_002_reference_data(conn: sqlite3.Connection) -> None:
    now = iso_now()
    conn.executemany(
        "INSERT INTO currencies(code, name_ar, name_en, symbol, decimal_places) VALUES (?, ?, ?, ?, ?)",
        CURRENCIES_V2,
    )
    conn.executemany(
        "INSERT INTO app_settings(key, value, value_type, updated_at) VALUES (?, ?, ?, ?)",
        [(key, value, value_type, now) for key, value, value_type in SETTINGS_V2],
    )
    conn.executemany(
        "INSERT INTO message_templates(name, channel, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        [(name, channel, body, now, now) for name, channel, body in TEMPLATES_V2],
    )
    conn.execute(
        "INSERT INTO schedules(name, kind, target, time_of_day, days_of_week, is_enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("تذكير يومي بالديون المستحقة", "reminder", "all", "09:00", "0,1,2,3,4,5,6", 0, now, now),
    )


MIGRATIONS: tuple[tuple[int, str, callable], ...] = (
    (1, "initial_schema", _migration_001_initial_schema),
    (2, "reference_data", _migration_002_reference_data),
)


def schema_version(db: Database) -> int:
    row = db.query_one("PRAGMA user_version")
    return int(row[0]) if row else 0


def applied_migrations(db: Database) -> list[dict]:
    rows = db.query("SELECT version, name, applied_at FROM schema_migrations ORDER BY version")
    return [dict(row) for row in rows]


def apply_migrations(db: Database) -> int:
    """Apply all pending migrations and return the resulting schema version."""
    conn = db.connection
    with db.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
    applied = {
        int(row["version"])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, name, migrate in MIGRATIONS:
        if version in applied:
            continue
        with db.transaction():
            migrate(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, iso_now()),
            )
    if not conn.in_transaction:
        conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
    return LATEST_VERSION
