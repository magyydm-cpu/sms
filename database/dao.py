"""Data access objects.

Every DAO receives an open connection and never commits by itself: the service
layer owns the transaction boundaries.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from core import calculations, money
from core.number_utils import phone_digits
from core.text_utils import name_key as make_name_key
from core.time_utils import iso_now
from database.models import Currency, Debt, Debtor, Installment, Payment


def row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def _now() -> str:
    return iso_now()


class DebtorDAO:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        *,
        name: str,
        name_key: str,
        original_phone: str,
        display_phone: str,
        phone_key: str,
        notes: str = "",
    ) -> int:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO debtors(name, name_key, original_phone, display_phone, phone_key, notes,
                                is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (name, name_key, original_phone, display_phone, phone_key, notes, now, now),
        )
        return int(cursor.lastrowid)

    def update(self, debtor_id: int, /, **fields) -> None:
        allowed = {
            "name",
            "name_key",
            "original_phone",
            "display_phone",
            "phone_key",
            "notes",
            "is_active",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [_now(), int(debtor_id)]
        self.conn.execute(
            f"UPDATE debtors SET {assignments}, updated_at = ? WHERE id = ?", params
        )

    def get_row(self, debtor_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM debtors WHERE id = ?", (int(debtor_id),)).fetchone()
        return row_to_dict(row)

    def get(self, debtor_id: int) -> Debtor | None:
        row = self.conn.execute("SELECT * FROM debtors WHERE id = ?", (int(debtor_id),)).fetchone()
        return Debtor.from_row(row) if row else None

    def search(self, text: str = "") -> list[Debtor]:
        sql = "SELECT * FROM debtors WHERE is_active = 1"
        params: list[Any] = []
        text = (text or "").strip()
        if text:
            clauses = ["name_key LIKE ?"]
            params.append(f"%{make_name_key(text)}%")
            digits = phone_digits(text)
            if digits:
                clauses.append("phone_key LIKE ?")
                params.append(f"%{digits}%")
            sql += " AND (" + " OR ".join(clauses) + ")"
        sql += " ORDER BY name_key ASC, id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return [Debtor.from_row(row) for row in rows]

    def find_by_phone_key(self, phone_key: str, exclude_id: int | None = None) -> Debtor | None:
        if not phone_key:
            return None
        sql = "SELECT * FROM debtors WHERE phone_key = ?"
        params: list[Any] = [phone_key]
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(int(exclude_id))
        sql += " LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        return Debtor.from_row(row) if row else None

    def find_similar_phone(self, digits: str, exclude_id: int | None = None) -> list[Debtor]:
        """Candidates whose cleaned number ends with/starts with the given digits."""
        if not digits or len(digits) < 7:
            return []
        sql = """
            SELECT * FROM debtors
            WHERE phone_key <> '' AND (phone_key LIKE ? OR ? LIKE '%' || phone_key)
        """
        params: list[Any] = [f"%{digits}", digits]
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(int(exclude_id))
        sql += " ORDER BY id"
        return [Debtor.from_row(row) for row in self.conn.execute(sql, params).fetchall()]

    def delete(self, debtor_id: int) -> None:
        self.conn.execute("DELETE FROM debtors WHERE id = ?", (int(debtor_id),))

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM debtors WHERE is_active = 1").fetchone()
        return int(row[0]) if row else 0


class CurrencyDAO:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_active(self) -> list[Currency]:
        rows = self.conn.execute(
            "SELECT * FROM currencies WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        return [Currency.from_row(row) for row in rows]

    def get(self, code: str) -> Currency | None:
        row = self.conn.execute(
            "SELECT * FROM currencies WHERE code = ?", (str(code or "").upper(),)
        ).fetchone()
        return Currency.from_row(row) if row else None

    def codes(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT code FROM currencies WHERE is_active = 1 ORDER BY code"
        ).fetchall()
        return [row["code"] for row in rows]


class DebtDAO:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        *,
        debtor_id: int,
        amount_minor: int,
        currency: str,
        debt_date: str,
        due_date: str | None,
        notes: str = "",
        status: str = calculations.STATUS_OPEN,
    ) -> int:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO debts(debtor_id, original_amount_minor, currency, debt_date, due_date,
                              status, has_installments, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (int(debtor_id), int(amount_minor), currency, debt_date, due_date, status, notes, now, now),
        )
        return int(cursor.lastrowid)

    def update(self, debt_id: int, /, **fields) -> None:
        allowed = {
            "original_amount_minor",
            "currency",
            "debt_date",
            "due_date",
            "notes",
            "status",
            "closed_at",
            "has_installments",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [_now(), int(debt_id)]
        self.conn.execute(f"UPDATE debts SET {assignments}, updated_at = ? WHERE id = ?", params)

    def get_row(self, debt_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM debts WHERE id = ?", (int(debt_id),)).fetchone()
        return row_to_dict(row)

    def get(self, debt_id: int) -> Debt | None:
        row = self.conn.execute("SELECT * FROM debts WHERE id = ?", (int(debt_id),)).fetchone()
        return Debt.from_row(row) if row else None

    def list_by_debtor(self, debtor_id: int) -> list[Debt]:
        rows = self.conn.execute(
            "SELECT * FROM debts WHERE debtor_id = ? ORDER BY debt_date DESC, id DESC",
            (int(debtor_id),),
        ).fetchall()
        return [Debt.from_row(row) for row in rows]

    def list_all(self, status: str | None = None) -> list[Debt]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM debts WHERE status = ? ORDER BY debt_date DESC, id DESC", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM debts ORDER BY debt_date DESC, id DESC"
            ).fetchall()
        return [Debt.from_row(row) for row in rows]

    def delete(self, debt_id: int) -> None:
        self.conn.execute("DELETE FROM debts WHERE id = ?", (int(debt_id),))

    def total_paid_minor(self, debt_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) FROM payments WHERE debt_id = ?", (int(debt_id),)
        ).fetchone()
        return int(row[0]) if row else 0

    def count_for_debtor(self, debtor_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM debts WHERE debtor_id = ?", (int(debtor_id),)
        ).fetchone()
        return int(row[0]) if row else 0


class PaymentDAO:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        *,
        debt_id: int,
        amount_minor: int,
        currency: str,
        paid_at: str,
        receipt_no: str,
        notes: str = "",
        installment_id: int | None = None,
    ) -> int:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO payments(debt_id, installment_id, amount_minor, currency, paid_at,
                                 receipt_no, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(debt_id),
                int(installment_id) if installment_id is not None else None,
                int(amount_minor),
                currency,
                paid_at,
                receipt_no,
                notes,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def get(self, payment_id: int) -> Payment | None:
        row = self.conn.execute("SELECT * FROM payments WHERE id = ?", (int(payment_id),)).fetchone()
        return Payment.from_row(row) if row else None

    def list_by_debt(self, debt_id: int) -> list[Payment]:
        rows = self.conn.execute(
            "SELECT * FROM payments WHERE debt_id = ? ORDER BY paid_at DESC, id DESC",
            (int(debt_id),),
        ).fetchall()
        return [Payment.from_row(row) for row in rows]

    def total_paid_minor(self, debt_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) FROM payments WHERE debt_id = ?", (int(debt_id),)
        ).fetchone()
        return int(row[0]) if row else 0

    def delete(self, payment_id: int) -> None:
        self.conn.execute("DELETE FROM payments WHERE id = ?", (int(payment_id),))


class InstallmentDAO:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_many(self, rows: Iterable[dict]) -> None:
        now = _now()
        payload = [
            (
                int(row["debt_id"]),
                int(row["seq"]),
                int(row["amount_minor"]),
                row["due_date"],
                "pending",
                row.get("notes", ""),
                now,
                now,
            )
            for row in rows
        ]
        self.conn.executemany(
            """
            INSERT INTO installments(debt_id, seq, amount_minor, due_date, status, notes,
                                     created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )

    def list_by_debt(self, debt_id: int) -> list[Installment]:
        rows = self.conn.execute(
            "SELECT * FROM installments WHERE debt_id = ? ORDER BY seq ASC", (int(debt_id),)
        ).fetchall()
        return [Installment.from_row(row) for row in rows]

    def get(self, installment_id: int) -> Installment | None:
        row = self.conn.execute(
            "SELECT * FROM installments WHERE id = ?", (int(installment_id),)
        ).fetchone()
        return Installment.from_row(row) if row else None

    def mark_paid(self, installment_id: int, paid_at: str, payment_id: int) -> None:
        self.conn.execute(
            """
            UPDATE installments
            SET status = 'paid', paid_at = ?, payment_id = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (paid_at, int(payment_id), _now(), int(installment_id)),
        )

    def cancel_pending(self, debt_id: int) -> int:
        cursor = self.conn.execute(
            "UPDATE installments SET status = 'cancelled', updated_at = ? "
            "WHERE debt_id = ? AND status = 'pending'",
            (_now(), int(debt_id)),
        )
        return cursor.rowcount

    def delete_for_debt(self, debt_id: int) -> None:
        self.conn.execute("DELETE FROM installments WHERE debt_id = ?", (int(debt_id),))

    def count_for_debt(self, debt_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM installments WHERE debt_id = ?", (int(debt_id),)
        ).fetchone()
        return int(row[0]) if row else 0

    def paid_count(self, debt_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM installments WHERE debt_id = ? AND status = 'paid'",
            (int(debt_id),),
        ).fetchone()
        return int(row[0]) if row else 0

    def sum_minor(self, debt_id: int, include_cancelled: bool = False) -> int:
        clause = "" if include_cancelled else " AND status <> 'cancelled'"
        row = self.conn.execute(
            f"SELECT COALESCE(SUM(amount_minor), 0) FROM installments WHERE debt_id = ?{clause}",
            (int(debt_id),),
        ).fetchone()
        return int(row[0]) if row else 0

    def has_any(self, debt_id: int) -> bool:
        return self.count_for_debt(debt_id) > 0


class SequenceDAO:
    """Monotonic counters (receipt numbers, ...). Works on old SQLite versions."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def next(self, name: str) -> int:
        cursor = self.conn.execute("UPDATE sequences SET value = value + 1 WHERE name = ?", (name,))
        if cursor.rowcount == 0:
            self.conn.execute("INSERT INTO sequences(name, value) VALUES (?, 1)", (name,))
            return 1
        row = self.conn.execute("SELECT value FROM sequences WHERE name = ?", (name,)).fetchone()
        return int(row[0])


def record_audit(
    conn: sqlite3.Connection,
    entity: str,
    action: str,
    entity_id: Any = "",
    before: dict | None = None,
    after: dict | None = None,
    actor: str = "local",
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs(entity, entity_id, action, actor, before_json, after_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity,
            str(entity_id),
            action,
            actor,
            json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
            json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
            _now(),
        ),
    )


def recalculate_debt_status(conn: sqlite3.Connection, debt_id: int) -> tuple[str, int]:
    """Recompute and persist a debt status from its payments.

    Also closes the installment plan (cancels pending installments) when the
    debt is fully paid, so no reminder can be generated for a settled debt.
    """
    row = conn.execute(
        "SELECT original_amount_minor, currency, status FROM debts WHERE id = ?", (int(debt_id),)
    ).fetchone()
    if row is None:
        raise KeyError(f"debt {debt_id} not found")
    paid_minor = PaymentDAO(conn).total_paid_minor(debt_id)
    total = money.from_minor(int(row["original_amount_minor"]), row["currency"])
    paid = money.from_minor(paid_minor, row["currency"])
    status = calculations.debt_status(total, paid)
    now = _now()
    if status == calculations.STATUS_PAID:
        conn.execute(
            "UPDATE debts SET status = ?, closed_at = COALESCE(closed_at, ?), updated_at = ? WHERE id = ?",
            (status, now, now, int(debt_id)),
        )
        conn.execute(
            "UPDATE installments SET status = 'cancelled', updated_at = ? "
            "WHERE debt_id = ? AND status = 'pending'",
            (now, int(debt_id)),
        )
    else:
        conn.execute(
            "UPDATE debts SET status = ?, closed_at = NULL, updated_at = ? WHERE id = ?",
            (status, now, int(debt_id)),
        )
    return status, paid_minor
