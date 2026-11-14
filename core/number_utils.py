"""Number and phone-number helpers.

Phone-number policy (fixed from the start of the project):
* the value the user typed is stored untouched in ``debtors.original_phone``;
* ``display_phone`` is a lightly formatted, human readable version;
* ``phone_key`` is the cleaned comparison key used for duplicate prevention.

Cleaning never changes the stored original. It only converts Arabic-Indic /
Eastern-Arabic digits to Latin digits, drops formatting characters and a
leading ``+`` / ``00`` prefix. No country code is ever forced.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

WESTERN_DIGITS = "0123456789"
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"      # U+0660..U+0669
EASTERN_ARABIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"    # U+06F0..U+06F9

_DIGIT_MAP: dict[int, str] = {}
for _index in range(10):
    _DIGIT_MAP[ord(ARABIC_INDIC_DIGITS[_index])] = str(_index)
    _DIGIT_MAP[ord(EASTERN_ARABIC_DIGITS[_index])] = str(_index)

MIN_PHONE_DIGITS = 5
MAX_PHONE_DIGITS = 20
# Shortest suffix that is still considered "the same number" when one side has a
# country code and the other one does not.
SUFFIX_MATCH_MIN_DIGITS = 7


def to_western_digits(text) -> str:
    """Convert any Arabic-Indic/Eastern-Arabic (or other Unicode) digits to 0-9."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    output = []
    for char in text:
        if ord(char) in _DIGIT_MAP:
            output.append(_DIGIT_MAP[ord(char)])
        elif char.isdigit() and char not in WESTERN_DIGITS:
            try:
                output.append(str(unicodedata.digit(char)))
            except (TypeError, ValueError):
                output.append(char)
        else:
            output.append(char)
    return "".join(output)


def phone_digits(raw) -> str:
    """Return only the Latin digits of a phone number (formatting removed)."""
    return "".join(char for char in to_western_digits(raw) if char in WESTERN_DIGITS)


def normalize_phone(raw) -> str:
    """Comparison key for duplicate detection.

    ``+964 770 123 4567``, ``00964-770-123-4567`` and ``9647701234567`` all map to
    ``9647701234567``. A local ``07701234567`` stays ``07701234567`` (no country
    code is guessed).
    """
    digits = phone_digits(raw)
    if digits.startswith("00") and len(digits) > 2:
        digits = digits[2:]
    return digits


def _group_from_left(digits: str, first_chunk: int = 3) -> str:
    """Group digits left-to-right, avoiding a lonely final digit."""
    if len(digits) <= first_chunk:
        return digits
    chunks = [digits[:first_chunk]]
    rest = digits[first_chunk:]
    chunks.extend(rest[index:index + 3] for index in range(0, len(rest), 3))
    if len(chunks) > 2 and len(chunks[-1]) == 1:
        chunks[-2] += chunks[-1]
        chunks.pop()
    return " ".join(chunks)


def format_phone_display(raw) -> str:
    """Human readable version of a phone number (keeps a leading +).

    If the user already typed separators we keep their grouping (only digits
    are converted); otherwise a readable grouping is generated. This field is
    for display only - the untouched value lives in ``original_phone``.
    """
    text = to_western_digits(str(raw or "")).strip()
    if not text:
        return ""
    digits = phone_digits(text)
    if not digits:
        return text
    if re.search(r"[\s\-().]", text):
        return re.sub(r"\s+", " ", text)
    if text.startswith("+"):
        return "+" + _group_from_left(digits, 3)
    return _group_from_left(digits, 4)


def is_probable_same_number(first, second) -> bool:
    """True when two inputs very likely denote the same phone number.

    Exact normalized equality always matches. As a safety net, a suffixed match
    is accepted when both have at least ``SUFFIX_MATCH_MIN_DIGITS`` digits (e.g.
    ``+9647701234567`` vs ``07701234567``: the second is not a suffix, so those
    two are *not* reported - country-code guessing is intentionally out of scope).
    """
    a = normalize_phone(first)
    b = normalize_phone(second)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= SUFFIX_MATCH_MIN_DIGITS and len(b) >= SUFFIX_MATCH_MIN_DIGITS:
        return a.endswith(b) or b.endswith(a)
    return False


def remove_thousands_separators(text: str) -> str:
    # U+066C Arabic thousands separator, ASCII comma, spaces and NBSP.
    return (
        to_western_digits(text)
        .replace("\u066c", "")
        .replace(",", "")
        .replace("\u00a0", "")
        .replace(" ", "")
    )


def parse_decimal(raw) -> Decimal:
    """Parse user input (Arabic digits, Arabic decimal separator, separators) to Decimal.

    Raises ``ValueError`` for unparseable input.
    """
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):  # never used for money math, only tolerant parsing
        return Decimal(str(raw))
    if raw is None:
        raise ValueError("empty amount")
    text = remove_thousands_separators(str(raw))
    text = text.replace("\u066b", ".")  # Arabic decimal separator
    text = re.sub(r"[^0-9.\-+]", "", text)
    if text in ("", "-", "+", ".", "-.", "+."):
        raise ValueError("invalid amount")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
