from __future__ import annotations

from decimal import Decimal

import pytest

from core import calculations, money, validation
from core.number_utils import (
    format_phone_display,
    is_probable_same_number,
    normalize_phone,
    parse_decimal,
    phone_digits,
    to_western_digits,
)


class TestDigitsAndPhones:
    def test_arabic_indic_digits_converted(self):
        assert to_western_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"
        assert to_western_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
        assert to_western_digits("رقم ١٢٣") == "رقم 123"

    def test_normalize_phone_strips_formatting_and_prefix(self):
        assert normalize_phone("+964 770 123 4567") == "9647701234567"
        assert normalize_phone("00964-770-123-4567") == "9647701234567"
        assert normalize_phone("(0770) 123 4567") == "07701234567"

    def test_normalize_phone_keeps_local_number_untouched(self):
        # No country code is ever guessed or added.
        assert normalize_phone("07701234567") == "07701234567"
        assert normalize_phone("٠٧٧٠١٢٣٤٥٦٧") == "07701234567"

    def test_phone_digits(self):
        assert phone_digits("+964 (770) 123-4567") == "9647701234567"

    def test_display_preserves_user_grouping(self):
        assert format_phone_display("+964 770 123 4567") == "+964 770 123 4567"
        assert format_phone_display("٠٧٧٠ ١٢٣ ٤٥٦٧") == "0770 123 4567"

    def test_display_adds_grouping_when_missing(self):
        assert format_phone_display("07701234567") == "0770 123 4567"
        assert format_phone_display("+9647701234567") == "+964 770 123 4567"

    def test_similar_number_detection(self):
        assert is_probable_same_number("+964 770 123 4567", "00964-770-123-4567")
        assert not is_probable_same_number("07701234567", "07709999999")


class TestMoney:
    def test_parse_decimal_accepts_arabic_input(self):
        assert parse_decimal("١٬٢٥٠٫٥٠") == Decimal("1250.50")
        assert parse_decimal("1,250.50") == Decimal("1250.50")
        assert money.parse_amount("250") == Decimal("250")

    def test_minor_unit_roundtrip(self):
        for currency, amount in (
            ("USD", "1234.56"),
            ("KWD", "99.125"),
            ("IQD", "1500"),
        ):
            minor = money.to_minor(Decimal(amount), currency)
            assert money.from_minor(minor, currency) == Decimal(amount)

    def test_no_float_math(self):
        assert money.to_minor(Decimal("0.10"), "USD") + money.to_minor(
            Decimal("0.20"), "USD"
        ) == money.to_minor(Decimal("0.30"), "USD")

    def test_format_amount(self):
        assert money.format_amount(Decimal("1250.5"), "USD") == "1,250.50"
        assert money.format_amount(Decimal("1500"), "IQD") == "1,500"


class TestValidation:
    def test_phone_returns_original_display_and_key(self):
        original, display, key = validation.validate_phone(" ٠٧٧٠-١٢٣-٤٥٦٧ ")
        assert original == "٠٧٧٠-١٢٣-٤٥٦٧"
        assert key == "07701234567"
        assert display == "0770-123-4567"

    def test_phone_required_and_length(self):
        with pytest.raises(validation.ValidationError):
            validation.validate_phone("")
        with pytest.raises(validation.ValidationError):
            validation.validate_phone("123")

    def test_amount_rejects_excess_decimals_for_currency(self):
        with pytest.raises(validation.ValidationError):
            validation.validate_amount("100.5", "IQD")
        # 1500.0 equals 1500 with zero decimals, so it is accepted.
        assert validation.validate_amount("1500.0", "IQD") == Decimal("1500")
        assert validation.validate_amount("100.125", "KWD") == Decimal("100.125")
        with pytest.raises(validation.ValidationError):
            validation.validate_amount("100.1234", "KWD")

    def test_amount_must_be_positive(self):
        with pytest.raises(validation.ValidationError):
            validation.validate_amount("0", "USD")
        with pytest.raises(validation.ValidationError):
            validation.validate_amount("-5", "USD")

    def test_date_parsing_formats(self):
        assert validation.parse_date("2026-02-01").isoformat() == "2026-02-01"
        assert validation.parse_date("01/02/2026").isoformat() == "2026-02-01"
        assert validation.parse_date("٢٠٢٦-٠٢-٠١").isoformat() == "2026-02-01"

    def test_due_date_cannot_precede_debt_date(self):
        with pytest.raises(validation.ValidationError):
            validation.validate_due_date(
                validation.parse_date("2026-02-01"), validation.parse_date("2026-01-01")
            )
