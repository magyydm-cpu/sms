"""Shared KivyMD widgets for the RTL Arabic UI."""
from __future__ import annotations

from kivy.metrics import dp
from kivy.properties import StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDIconButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

from core import calculations, money
from ui.arabic import T, font_kwargs, fonts_available

PRIMARY = (0.0, 0.47, 0.45, 1)
DANGER = (0.78, 0.16, 0.16, 1)
MUTED = (0.38, 0.38, 0.38, 1)
SUCCESS = (0.11, 0.53, 0.30, 1)
WARNING = (0.80, 0.47, 0.03, 1)

STATUS_COLORS = {
    calculations.STATUS_OPEN: DANGER,
    calculations.STATUS_PARTIALLY_PAID: WARNING,
    calculations.STATUS_PAID: SUCCESS,
    calculations.STATUS_CANCELLED: MUTED,
    calculations.INSTALLMENT_PENDING: MUTED,
    calculations.INSTALLMENT_OVERDUE: DANGER,
    calculations.INSTALLMENT_PAID: SUCCESS,
    calculations.INSTALLMENT_CANCELLED: MUTED,
}


class RTLBoxLayout(MDBoxLayout):
    """Horizontal box whose first added child appears on the right."""

    def add_widget(self, widget, index=0, canvas=None):
        if self.orientation == "horizontal":
            index = len(self.children)
        return super().add_widget(widget, index=index, canvas=canvas)


class LabeledField(MDBoxLayout):
    """RTL-friendly form field: an Arabic label above a Material text field.

    KivyMD 1.2 draws MDTextField's floating hint at the left edge, which looks
    wrong in an Arabic form. This wrapper keeps the same ``.text`` interface
    used by the screens while placing the label on the right.
    """

    text = StringProperty("")

    def __init__(
        self, label, text="", multiline=False, field_height=None, preview=False, **kwargs
    ):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", dp(3))
        super().__init__(**kwargs)
        self._preview = preview
        self.label = ArLabel(
            text=label,
            font_size="13sp",
            theme_text_color="Secondary",
            size_hint_y=None,
            height=dp(26),
        )
        field_kwargs = {
            "text": text,
            "hint_text": "",
            "mode": "rectangle",
            "multiline": multiline,
            "size_hint_y": None,
            "halign": "right",
            **font_kwargs(),
        }
        if field_height:
            field_kwargs["height"] = field_height
        self.field = MDTextField(**field_kwargs)
        self.field.bind(text=self._on_field_text)
        self.bind(text=self._on_self_text)
        self.add_widget(self.label)
        self.add_widget(self.field)
        self.preview_label = None
        if preview:
            # Kivy's SDL2 TextInput cannot reorder bidi text while editing, so a
            # live shaped preview confirms exactly what will be stored.
            self.preview_label = ArLabel(
                text="",
                font_size="12sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(24),
            )
            self.add_widget(self.preview_label)
            self.field.bind(text=self._update_preview)
            self._update_preview()
        # MDTextField enforces its own minimum height (69dp), so the container
        # must follow the real height instead of a hard-coded value.
        self.field.bind(height=self._sync_height)
        self.label.bind(height=self._sync_height)
        self._sync_height()

    def _sync_height(self, *_args):
        height = self.label.height + self.field.height + self.spacing
        if self.preview_label is not None:
            height += self.preview_label.height + self.spacing
        if self.height != height:
            self.height = height

    def _update_preview(self, *_args):
        if self.preview_label is None:
            return
        text = (self.field.text or "").strip()
        self.preview_label.set_text(f"كما سيُحفظ: {text}" if text else "")

    def _on_field_text(self, *_args):
        if self.text != self.field.text:
            self.text = self.field.text

    def _on_self_text(self, *_args):
        if self.field.text != self.text:
            self.field.text = self.text


class ArLabel(MDLabel):
    """Arabic-capable label: shapes text, right aligns and sizes text to itself."""

    def __init__(self, **kwargs):
        text = kwargs.pop("text", "")
        if fonts_available():
            kwargs.setdefault("font_name", "Arabic")
        kwargs.setdefault("halign", "right")
        super().__init__(text=T(text), **kwargs)
        self.bind(width=self._sync_text_size, height=self._sync_text_size)
        self._sync_text_size()

    def _sync_text_size(self, *_args):
        self.text_size = (self.width, self.height)

    def set_text(self, text) -> None:
        self.text = T(text)


class ClickableCard(MDCard):
    """MDCard with a simple tap callback (child buttons still work)."""

    def __init__(self, on_click=None, **kwargs):
        self._on_click = on_click
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        if self._on_click and self.collide_point(*touch.pos):
            touch.grab(self)
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if self._on_click and self.collide_point(*touch.pos):
                self._on_click()
            return True
        return super().on_touch_up(touch)


def make_top_bar(title, on_back=None, actions=None):
    left = [["arrow-right", lambda *_: on_back()]] if on_back else []
    bar = MDTopAppBar(
        title=T(title),
        left_action_items=left,
        right_action_items=actions or [],
        elevation=1,
        size_hint_y=None,
        height=dp(60),
    )
    return bar


def make_scroll(padding_bottom=dp(110)):
    scroll = MDScrollView()
    box = MDBoxLayout(
        orientation="vertical",
        adaptive_height=True,
        spacing=dp(8),
        padding=[dp(12), dp(24), dp(12), padding_bottom],
    )
    box.bind(minimum_height=box.setter("height"))
    scroll.add_widget(box)
    return scroll, box


def info_row(label_text, value_text, value_color=None):
    row = RTLBoxLayout(
        orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6)
    )
    value_kwargs = {"font_size": "15sp", "size_hint_x": 0.62, "halign": "left"}
    if value_color:
        value_kwargs.update(color=value_color, theme_text_color="Custom")
    value = ArLabel(text=value_text, **value_kwargs)
    label = ArLabel(
        text=label_text, font_size="13sp", size_hint_x=0.38, theme_text_color="Secondary"
    )
    # First added child is placed on the right by RTLBoxLayout: label right,
    # value on the left.
    row.add_widget(label)
    row.add_widget(value)
    return row


def section_title(text):
    return ArLabel(
        text=text,
        font_size="16sp",
        bold=True,
        size_hint_y=None,
        height=dp(32),
        theme_text_color="Primary",
    )


def status_chip(text, status):
    return ArLabel(
        text=text,
        font_size="12sp",
        theme_text_color="Custom",
        color=STATUS_COLORS.get(status, MUTED),
        size_hint=(None, None),
        height=dp(24),
        width=dp(100),
    )


def empty_label(text):
    return ArLabel(
        text=text,
        font_size="14sp",
        theme_text_color="Secondary",
        size_hint_y=None,
        height=dp(70),
    )


def show_message(title, text, on_close=None):
    dialog = MDDialog(
        title=T(title),
        text=T(text),
        buttons=[
            MDFlatButton(
                text=T("حسناً"),
                on_release=lambda *_: (
                    dialog.dismiss(),
                    on_close() if on_close else None,
                ),
            )
        ],
    )
    dialog.open()


def confirm(title, text, on_confirm, confirm_text="تأكيد"):
    def _do_confirm(*_args):
        dialog.dismiss()
        on_confirm()

    dialog = MDDialog(
        title=T(title),
        text=T(text),
        buttons=[
            MDFlatButton(text=T("إلغاء"), on_release=lambda *_: dialog.dismiss()),
            MDFlatButton(text=T(confirm_text), on_release=_do_confirm),
        ],
    )
    dialog.open()


def money_text(value, currency):
    return money.format_money(value, currency)


def totals_lines(totals: dict) -> str:
    if not totals:
        return "لا توجد ديون مسجلة"
    lines = []
    for currency in sorted(totals):
        bucket = totals[currency]
        lines.append(
            f"{money.format_amount(bucket['remaining'], currency)} {currency}"
        )
    return "المتبقي: " + " + ".join(lines)


def icon_button(icon, callback, tooltip=""):
    # MDIconButton (KivyMD 1.2) has no tooltip_text property; the parameter is
    # kept for call-site readability and future use with MDTooltip.
    return MDIconButton(
        icon=icon,
        size_hint_x=None,
        width=dp(44),
        on_release=lambda *_: callback(),
    )


def make_field(hint, text="", multiline=False, height=None, preview=False, **kwargs):
    """RTL form field (right-aligned label above the input)."""
    return LabeledField(
        hint,
        text=text,
        multiline=multiline,
        field_height=height,
        preview=preview,
        **kwargs,
    )


def make_button(text, callback, **kwargs):
    kwargs.pop("size_hint", None)
    button = MDRaisedButton(
        text=T(text), on_release=lambda *_: callback(), height=dp(48), **kwargs
    )
    # KivyMD's KV rule sets size_hint=(None, None); override it after creation so
    # primary actions stretch across the form width.
    button.size_hint = (1, None)
    return button


def action_row(*buttons):
    row = RTLBoxLayout(
        orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8)
    )
    for button in buttons:
        row.add_widget(button)
    return row
