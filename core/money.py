"""Exact money handling.

Every monetary amount is stored in SQLite as an integer number of **minor
units** (``amount_minor``) - e.g. 12.50 USD is stored as ``1250`` - and every
calculation is performed with :class:`decimal.Decimal`. Floating point values
are never used for money.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .number_utils import parse_decimal, to_western_digits

DEFAULT_DECIMALS = 2

# Seeded into the `currencies` table; the DB row is the source of truth at
# runtime, these defaults are used by pure calculation helpers/tests.
CURRENCY_META: dict[str, dict] = {
    "IQD": {"decimals": 0, "symbol": "د.ع", "name_ar": "دينار عراقي"},
    "USD": {"decimals": 2, "symbol": "$", "name_ar": "دولار أمريكي"},
    "EUR": {"decimals": 2, "symbol": "€", "name_ar": "يورو"},
    "GBP": {"decimals": 2, "symbol": "£", "name_ar": "جنيه إسترليني"},
    "SAR": {"decimals": 2, "symbol": "ر.س", "name_ar": "ريال سعودي"},
    "AED": {"decimals": 2, "symbol": "د.إ", "name_ar": "درهم إماراتي"},
    "KWD": {"decimals": 3, "symbol": "د.ك", "name_ar": "دينار كويتي"},
    "JOD": {"decimals": 3, "symbol": "د.أ", "name_ar": "دينار أردني"},
    "EGP": {"decimals": 2, "symbol": "ج.م", "name_ar": "جنيه مصري"},
    "TRY": {"decimals": 2, "symbol": "₺", "name_ar": "ليرة تركية"},
}


def decimals_for(currency: str | None) -> int:
    if not currency:
        return DEFAULT_DECIMALS
    meta = CURRENCY_META.get(str(currency).upper())
    return int(meta["decimals"]) if meta else DEFAULT_DECIMALS


def symbol_for(currency: str | None) -> str:
    meta = CURRENCY_META.get(str(currency or "").upper())
    return str(meta["symbol"]) if meta else str(currency or "")


def _coerce_decimals(currency_or_decimals) -> int:
    if isinstance(currency_or_decimals, int):
        return currency_or_decimals
    if isinstance(currency_or_decimals, str) and currency_or_decimals.isdigit():
        return int(currency_or_decimals)
    return decimals_for(str(currency_or_decimals) if currency_or_decimals else None)


def quantize(value, currency_or_decimals=DEFAULT_DECIMALS) -> Decimal:
    """Round a Decimal to the currency's precision (half-up, banker's rounding is unwanted here)."""
    decimals = _coerce_decimals(currency_or_decimals)
    exponent = Decimal(1).scaleb(-decimals)
    return Decimal(value).quantize(exponent, rounding=ROUND_HALF_UP)


def to_minor(value, currency_or_decimals=DEFAULT_DECIMALS) -> int:
    """Convert a Decimal amount to integer minor units for storage."""
    decimals = _coerce_decimals(currency_or_decimals)
    quantized = quantize(value, decimals)
    return int(quantized.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))


def from_minor(minor: int | None, currency_or_decimals=DEFAULT_DECIMALS) -> Decimal:
    """Rebuild a Decimal amount from integer minor units."""
    decimals = _coerce_decimals(currency_or_decimals)
    if minor is None:
        minor = 0
    return Decimal(int(minor)).scaleb(-decimals)


def parse_amount(raw) -> Decimal:
    """Parse arbitrary user input into a Decimal (Arabic digits supported)."""
    return parse_decimal(raw)


def format_amount(
    value,
    currency: str | None = None,
    decimals: int | None = None,
    grouping: bool = True,
) -> str:
    """Format an amount with thousands separators, no float conversion."""
    places = decimals if decimals is not None else decimals_for(currency)
    amount = quantize(value, places)
    pattern = f",.{places}f" if grouping else f".{places}f"
    return format(amount, pattern)


def format_money(value, currency: str, decimals: int | None = None) -> str:
    """``1,250.00 USD`` style display string (currency code kept explicit)."""
    return f"{format_amount(value, currency, decimals)} {currency or ''}".strip()


def to_text(value, currency: str | None = None) -> str:
    """Plain, group-free decimal string (used for audit snapshots / export)."""
    places = decimals_for(currency)
    return format(quantize(value, places), f".{places}f")


def safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or value == "":
            return default
        return parse_decimal(to_western_digits(str(value)))
    except (InvalidOperation, ValueError):
        return default
