"""Debtor management."""
from __future__ import annotations

import sqlite3

from core import calculations, money, validation
from core.number_utils import normalize_phone
from core.text_utils import name_key as make_name_key
from database.dao import (
    DebtDAO,
    DebtorDAO,
    InstallmentDAO,
    PaymentDAO,
    record_audit,
)
from database.db import Database
from database.models import Debtor, DebtorSummary, DebtSummary
from services.errors import BusinessRuleError, DuplicateDebtorError, NotFoundError


class DebtorService:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list(self, search: str = "") -> list[DebtorSummary]:
        with self.db.transaction() as conn:
            debtor_dao = DebtorDAO(conn)
            debt_dao = DebtDAO(conn)
            payment_dao = PaymentDAO(conn)
            installment_dao = InstallmentDAO(conn)
            return [
                self._build_summary(debtor, debt_dao, payment_dao, installment_dao)
                for debtor in debtor_dao.search(search)
            ]

    def get(self, debtor_id: int) -> Debtor:
        with self.db.transaction() as conn:
            debtor = DebtorDAO(conn).get(debtor_id)
        if debtor is None:
            raise NotFoundError("المدين")
        return debtor

    def overview(self, debtor_id: int) -> DebtorSummary:
        with self.db.transaction() as conn:
            debtor_dao = DebtorDAO(conn)
            debtor = debtor_dao.get(debtor_id)
            if debtor is None:
                raise NotFoundError("المدين")
            return self._build_summary(
                debtor, DebtDAO(conn), PaymentDAO(conn), InstallmentDAO(conn)
            )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def create(self, name, phone, notes: str = "") -> Debtor:
        name = validation.validate_name(name)
        original_phone, display_phone, phone_key = validation.validate_phone(phone, required=True)
        notes = validation.validate_notes(notes)
        with self.db.transaction() as conn:
            dao = DebtorDAO(conn)
            existing = dao.find_by_phone_key(phone_key)
            if existing is not None:
                raise DuplicateDebtorError(existing)
            try:
                debtor_id = dao.insert(
                    name=name,
                    name_key=make_name_key(name),
                    original_phone=original_phone,
                    display_phone=display_phone,
                    phone_key=phone_key,
                    notes=notes,
                )
            except sqlite3.IntegrityError:
                # Race / direct DB insert: the partial unique index is the final guard.
                raise DuplicateDebtorError(dao.find_by_phone_key(phone_key)) from None
            record_audit(conn, "debtor", "create", debtor_id, after=dao.get_row(debtor_id))
            debtor = dao.get(debtor_id)
        assert debtor is not None
        return debtor

    def update(self, debtor_id: int, name, phone, notes: str = "") -> Debtor:
        name = validation.validate_name(name)
        original_phone, display_phone, phone_key = validation.validate_phone(phone, required=True)
        notes = validation.validate_notes(notes)
        with self.db.transaction() as conn:
            dao = DebtorDAO(conn)
            before = dao.get_row(debtor_id)
            if before is None:
                raise NotFoundError("المدين")
            conflict = dao.find_by_phone_key(phone_key, exclude_id=debtor_id)
            if conflict is not None:
                raise DuplicateDebtorError(conflict)
            try:
                dao.update(
                    debtor_id,
                    name=name,
                    name_key=make_name_key(name),
                    original_phone=original_phone,
                    display_phone=display_phone,
                    phone_key=phone_key,
                    notes=notes,
                )
            except sqlite3.IntegrityError:
                raise DuplicateDebtorError(dao.find_by_phone_key(phone_key)) from None
            record_audit(
                conn, "debtor", "update", debtor_id, before=before, after=dao.get_row(debtor_id)
            )
            debtor = dao.get(debtor_id)
        assert debtor is not None
        return debtor

    def delete(self, debtor_id: int) -> None:
        """Delete a debtor and (via FK cascade) all of their debts/payments.

        A full JSON snapshot is written to ``audit_logs`` first, so nothing is
        lost silently.
        """
        with self.db.transaction() as conn:
            dao = DebtorDAO(conn)
            snapshot = dao.get_row(debtor_id)
            if snapshot is None:
                raise NotFoundError("المدين")
            debts = DebtDAO(conn).list_by_debtor(debtor_id)
            snapshot["debts"] = [
                {
                    "id": debt.id,
                    "amount_minor": debt.amount_minor,
                    "currency": debt.currency,
                    "debt_date": debt.debt_date,
                    "due_date": debt.due_date,
                    "status": debt.status,
                }
                for debt in debts
            ]
            record_audit(conn, "debtor", "delete", debtor_id, before=snapshot)
            dao.delete(debtor_id)

    # ------------------------------------------------------------------
    # Duplicate helpers (used by the UI for a friendlier warning)
    # ------------------------------------------------------------------
    def check_phone_conflict(self, phone, exclude_id: int | None = None) -> Debtor | None:
        key = normalize_phone(phone)
        if not key:
            return None
        with self.db.transaction() as conn:
            return DebtorDAO(conn).find_by_phone_key(key, exclude_id=exclude_id)

    def find_similar_numbers(self, phone, exclude_id: int | None = None) -> list[Debtor]:
        key = normalize_phone(phone)
        if not key:
            return []
        with self.db.transaction() as conn:
            return DebtorDAO(conn).find_similar_phone(key, exclude_id=exclude_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _build_summary(
        debtor: Debtor,
        debt_dao: DebtDAO,
        payment_dao: PaymentDAO,
        installment_dao: InstallmentDAO,
    ) -> DebtorSummary:
        debts = debt_dao.list_by_debtor(debtor.id)
        summaries: list[DebtSummary] = []
        entries: list[tuple[str, object, object]] = []
        for debt in debts:
            paid_minor = payment_dao.total_paid_minor(debt.id)
            total = debt.amount
            paid = money.from_minor(paid_minor, debt.currency)
            info = calculations.summarize(total, paid)
            installments = installment_dao.list_by_debt(debt.id)
            summaries.append(
                DebtSummary(
                    debt=debt,
                    total=info["total"],
                    paid=info["paid"],
                    remaining=info["remaining"],
                    status=info["status"],
                    installments_total=len(installments),
                    installments_paid=sum(1 for item in installments if item.status == "paid"),
                    installments_overdue=calculations.count_overdue(installments),
                )
            )
            entries.append((debt.currency, total, paid))
        return DebtorSummary(
            debtor=debtor,
            debts=summaries,
            totals=calculations.group_totals(entries),
        )
