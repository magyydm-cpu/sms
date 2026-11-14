"""Input validation with Arabic, user-facing error messages.

Validation functions raise :class:`ValidationError`; they never mutate the
stored values (the phone number is returned exactly as entered by the user).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from . import money
from .number_utils import format_phone_display, normalize_phone, phone_digits, to_western_digits

NAME_MAX_LENGTH = 120
NOTES_MAX_LENGTH = 2000
MIN_PHONE_DIGITS = 5
MAX_PHONE_DIGITS = 20


class ValidationError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def validate_name(value) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise ValidationError("الاسم مطلوب", "name")
    if len(text) > NAME_MAX_LENGTH:
        raise ValidationError(f"الاسم أطول من {NAME_MAX_LENGTH} حرف", "name")
    return text


def validate_notes(value) -> str:
    text = str(value or "").strip()
    if len(text) > NOTES_MAX_LENGTH:
        raise ValidationError(f"الملاحظات أطول من {NOTES_MAX_LENGTH} حرف", "notes")
    return text


def validate_phone(value, required: bool = True) -> tuple[str, str, str]:
    """Return ``(original, display, phone_key)``.

    The original string is preserved exactly; only surrounding whitespace is
    trimmed. No ``+`` or country code is added automatically.
    """
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValidationError("رقم الهاتف مطلوب", "phone")
        return "", "", ""
    digits = phone_digits(raw)
    if len(digits) < MIN_PHONE_DIGITS:
        raise ValidationError(f"رقم الهاتف قصير جداً (أقل من {MIN_PHONE_DIGITS} أرقام)", "phone")
    if len(digits) > MAX_PHONE_DIGITS:
        raise ValidationError(f"رقم الهاتف طويل جداً (أكثر من {MAX_PHONE_DIGITS} رقماً)", "phone")
    return raw, format_phone_display(raw), normalize_phone(raw)


def validate_amount(value, currency: str = "") -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = money.parse_amount(value)
        except (ValueError, InvalidOperation):
            raise ValidationError("المبلغ غير صالح", "amount") from None
    if amount <= 0:
        raise ValidationError("المبلغ يجب أن يكون أكبر من صفر", "amount")
    decimals = money.decimals_for(currency)
    if money.quantize(amount, decimals) != amount:
        raise ValidationError(
            f"العملة {currency or ''} لا تسمح بأكثر من {decimals} منزلة عشرية".strip(),
            "amount",
        )
    return amount


def validate_positive_int(value, field: str, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("يجب إدخال رقم صحيح", field) from None
    if number < minimum or number > maximum:
        raise ValidationError(f"القيمة يجب أن تكون بين {minimum} و {maximum}", field)
    return number


def parse_date(value, field: str = "التاريخ") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = to_western_digits(str(value or "")).strip()
    if not text:
        raise ValidationError("التاريخ مطلوب", field)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError("صيغة التاريخ غير صحيحة، استخدم YYYY-MM-DD", field)


def validate_due_date(debt_date: date, due_date: date | None) -> date | None:
    if due_date is not None and due_date < debt_date:
        raise ValidationError("تاريخ الاستحقاق لا يمكن أن يسبق تاريخ الدين", "due_date")
    return due_date


def validate_currency(code: str, allowed: list[str] | None = None) -> str:
    currency = str(code or "").strip().upper()
    if not currency:
        raise ValidationError("العملة مطلوبة", "currency")
    if allowed is not None and currency not in allowed:
        raise ValidationError(f"العملة {currency} غير مدعومة", "currency")
    return currency


def validate_receipt_no(value) -> str:
    text = str(value or "").strip()
    if len(text) > 60:
        raise ValidationError("رقم الإيصال أطول من 60 حرفاً", "receipt_no")
    return text


def validate_interval_months(value) -> int:
    months = validate_positive_int(value, "months_between", minimum=1, maximum=12)
    return months
