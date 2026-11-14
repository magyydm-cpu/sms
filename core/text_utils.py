"""Arabic-aware text normalization.

Used for de-duplicating and searching names without changing what is stored:
``أحمد``, ``احمد`` and ``أَحْمَد`` all normalize to the same search key.
"""
from __future__ import annotations

import re

_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_TATWEEL = "\u0640"
_FOLD = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
        "ۀ": "ه",
        "ک": "ك",
        "ی": "ي",
        "ە": "ه",
    }
)


def normalize_name(value) -> str:
    """Return a stable comparison key for a person/company name."""
    if value is None:
        return ""
    text = str(value).replace(_TATWEEL, "")
    text = _DIACRITICS.sub("", text)
    text = text.translate(_FOLD)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def name_key(value) -> str:
    return normalize_name(value)


def contains_text(haystack: str, needle: str) -> bool:
    if not needle:
        return True
    return needle in (haystack or "")
