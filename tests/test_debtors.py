from __future__ import annotations

import json

import pytest

from core import validation
from services.errors import DuplicateDebtorError, NotFoundError


class TestDebtorCreation:
    def test_original_phone_is_preserved_exactly(self, services):
        debtor = services.debtors.create("علي حسن", "+964 770 123 4567")
        assert debtor.original_phone == "+964 770 123 4567"
        assert debtor.phone_key == "9647701234567"
        assert debtor.display_phone == "+964 770 123 4567"

    def test_arabic_digits_are_kept_in_original(self, services):
        debtor = services.debtors.create("سارة", "٠٧٧٠١٢٣٤٥٦٧")
        assert debtor.original_phone == "٠٧٧٠١٢٣٤٥٦٧"
        assert debtor.phone_key == "07701234567"

    def test_validation_errors(self, services):
        with pytest.raises(validation.ValidationError):
            services.debtors.create("   ", "07701234567")
        with pytest.raises(validation.ValidationError):
            services.debtors.create("بلا هاتف", "")

    def test_not_found(self, services):
        with pytest.raises(NotFoundError):
            services.debtors.get(999)


class TestDuplicatePrevention:
    def test_same_number_with_different_formatting_is_rejected(self, services):
        services.debtors.create("أحمد", "+964 770 123 4567")
        with pytest.raises(DuplicateDebtorError) as error:
            services.debtors.create("أحمد آخر", "00964-770-123-4567")
        assert error.value.existing.name == "أحمد"

    def test_arabic_and_english_digits_are_the_same_number(self, services):
        services.debtors.create("أحمد", "07701234567")
        with pytest.raises(DuplicateDebtorError):
            services.debtors.create("أحمد ٢", "٠٧٧٠١٢٣٤٥٦٧")

    def test_update_to_existing_phone_is_rejected(self, services):
        first = services.debtors.create("الأول", "07701111111")
        second = services.debtors.create("الثاني", "07702222222")
        with pytest.raises(DuplicateDebtorError):
            services.debtors.update(second.id, "الثاني", "07701111111")
        # Unchanged phone for the same debtor is fine.
        updated = services.debtors.update(first.id, "الأول المعدل", "+964 770 111 1111")
        assert updated.name == "الأول المعدل"

    def test_empty_phone_cannot_be_duplicated_in_schema(self, services, db):
        # The service requires a phone, but the partial unique index also guards
        # direct DB writes with a cleaned key.
        services.debtors.create("مدين", "07703333333")
        with pytest.raises(Exception):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO debtors(name, name_key, original_phone, display_phone, phone_key, "
                    "notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("مكرر", "مكرر", "07703333333", "07703333333", "07703333333", "", "x", "x"),
                )


class TestSearchAndUpdate:
    def test_search_normalizes_arabic_letters(self, services):
        services.debtors.create("أحمد علي", "07701111111")
        services.debtors.create("منى", "07702222222")
        results = services.debtors.list("احمد")
        assert [item.debtor.name for item in results] == ["أحمد علي"]

    def test_search_by_phone_digits(self, services):
        services.debtors.create("أحمد علي", "07701111111")
        results = services.debtors.list("1111")
        assert len(results) == 1

    def test_notes_update(self, services, debtor):
        updated = services.debtors.update(debtor.id, debtor.name, debtor.original_phone, "ملاحظة جديدة")
        assert updated.notes == "ملاحظة جديدة"


class TestDeleteCascade:
    def test_delete_removes_debts_and_payments_and_audits(self, services, db):
        debtor = services.debtors.create("للحذف", "07704444444")
        debt = services.debts.create(debtor.id, "100.00", "USD")
        services.payments.add(debt.id, "25.00")
        services.debtors.delete(debtor.id)

        with db.transaction() as conn:
            assert conn.execute("SELECT COUNT(*) FROM debtors").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM debts").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0
            row = conn.execute(
                "SELECT before_json FROM audit_logs WHERE entity='debtor' AND action='delete'"
            ).fetchone()
        snapshot = json.loads(row["before_json"])
        assert snapshot["name"] == "للحذف"
        assert len(snapshot["debts"]) == 1
