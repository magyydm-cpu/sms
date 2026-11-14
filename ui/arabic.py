"""Arabic/RTL support for Kivy.

Kivy's SDL2 text provider has no built-in bidi reordering, so every Arabic
string that reaches a widget is reshaped (arabic_reshaper) and reordered
(python-bidi) by :func:`T`. The bundled Amiri font is registered under the
Roboto family names so all KivyMD widgets get Arabic glyphs, and ``Arabic`` is
available as an explicit font name.
"""
from __future__ import annotations

import os
from functools import lru_cache

from kivy.core.text import LabelBase

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")
# Amiri covers the full Arabic Presentation Forms block (FE70-FEFF), which is
# required because arabic_reshaper emits presentation-form codepoints. Amiri
# covers them; the previously bundled Tajawal omitted several (ا د ر و ة ن ط أ إ)
# and produced tofu boxes.
FONT_REGULAR = os.path.join(FONT_DIR, "Amiri-Regular.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "Amiri-Bold.ttf")
FONT_NAME = "Arabic"

_FONTS_READY = False
_SHAPING_AVAILABLE = False

try:  # optional at runtime, listed in requirements
    import arabic_reshaper
    from bidi.algorithm import get_display

    _SHAPING_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for minimal installs
    arabic_reshaper = None
    get_display = None


def register_fonts() -> bool:
    """Register the bundled Arabic font (idempotent). Returns True when available."""
    global _FONTS_READY
    if _FONTS_READY:
        return True
    if not os.path.exists(FONT_REGULAR):
        return False
    bold = FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_REGULAR
    LabelBase.register(
        name=FONT_NAME,
        fn_regular=FONT_REGULAR,
        fn_bold=bold,
        fn_italic=FONT_REGULAR,
        fn_bolditalic=bold,
    )
    # Override the Roboto family names used by KivyMD's default theme so every
    # widget (buttons, text fields, dialogs, menu items) can render Arabic.
    for name in ("Roboto", "RobotoRegular", "RobotoMedium", "RobotoLight", "RobotoThin", "RobotoBlack"):
        LabelBase.register(
            name=name,
            fn_regular=FONT_REGULAR,
            fn_bold=bold,
            fn_italic=FONT_REGULAR,
            fn_bolditalic=bold,
        )
    LabelBase.register(name="RobotoBold", fn_regular=bold, fn_bold=bold)
    _FONTS_READY = True
    return True


def fonts_available() -> bool:
    return _FONTS_READY


def font_kwargs() -> dict:
    """Widget kwargs that switch to the bundled Arabic font, when available."""
    return {"font_name": FONT_NAME} if _FONTS_READY else {}


@lru_cache(maxsize=4096)
def shape_arabic(text: str) -> str:
    if not text:
        return ""
    if not _SHAPING_AVAILABLE:
        return text
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:  # pragma: no cover - never break the UI over text shaping
        return str(text)


def T(text) -> str:
    """Shape/reorder a user-visible string for Kivy's LTR text renderer."""
    if text is None:
        return ""
    return shape_arabic(str(text))


def plain(text) -> str:
    """Return text unchanged (used for stored user data that must not be shaped)."""
    return "" if text is None else str(text)


def ltr(text) -> str:
    """Wrap a Latin/number run (phone, amount, date list) in LRM marks.

    In an RTL paragraph the bidi algorithm otherwise reorders the space
    separated groups of a phone number (``+964 770 123 4567`` would display as
    ``4567 123 770 964+``).
    """
    return f"\u200e{text}\u200e"
