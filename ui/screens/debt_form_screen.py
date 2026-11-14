"""Debt add/edit form screen."""
from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.list import OneLineListItem  # noqa: F401 - registers the menu item viewclass
from kivymd.uix.menu import MDDropdownMenu

from core import money
from core.time_utils import today_iso
from ui.arabic import T
from ui.screens.base import BaseScreen
from ui.widgets import ArLabel, make_button, make_field, make_scroll


class DebtFormScreen(BaseScreen):
    screen_name = "debt_form"
    screen_title = "بيانات الدين"

    def build(self) -> None:
        self.debtor_id = None
        self.debt_id = None
        self.currency = "IQD"
        self.currencies = []
        self.add_top_bar(
            "بيانات الدين", actions=[["content-save", lambda *_: self._save()]]
        )
        scroll, self.box = make_scroll(padding_bottom=dp(24))
        self.content.add_widget(scroll)

        self.amount_field = make_field("مبلغ الدين")
        self.currency_button = MDFlatButton(
            text=T("العملة: IQD"),
            size_hint_y=None,
            height=dp(48),
            halign="center",
            on_release=lambda *_: self._open_currency_menu(),
        )
        # Same KivyMD KV override as make_button: stretch after construction.
        self.currency_button.size_hint = (1, None)
        self.debt_date_field = make_field("تاريخ الدين (YYYY-MM-DD)")
        self.due_date_field = make_field("تاريخ الاستحقاق - اختياري (YYYY-MM-DD)")
        self.notes_field = make_field("ملاحظات", multiline=True, preview=True)

        self.box.add_widget(self.amount_field)
        self.box.add_widget(self.currency_button)
        self.box.add_widget(self.debt_date_field)
        self.box.add_widget(self.due_date_field)
        self.box.add_widget(self.notes_field)
        self.box.add_widget(make_button("حفظ", self._save))

    def load(self, debtor_id=None, debt_id=None, **kwargs) -> None:
        self.debtor_id = debtor_id
        self.debt_id = debt_id

    def refresh(self) -> None:
        if not hasattr(self, "amount_field"):
            return
        try:
            self.currencies = self.app.services.reference.currencies()
        except Exception as exc:
            self.handle_error(exc)
            return
        if self.debt_id:
            try:
                debt = self.app.services.debts.get(self.debt_id)
            except Exception as exc:
                self.handle_error(exc)
                return
            self.debtor_id = self.debtor_id or debt.debtor_id
            self.currency = debt.currency
            self.amount_field.text = money.format_amount(
                debt.amount, debt.currency, grouping=False
            )
            self.debt_date_field.text = debt.debt_date
            self.due_date_field.text = debt.due_date or ""
            self.notes_field.text = debt.notes
        else:
            default_currency = self.app.services.reference.default_currency()
            if default_currency not in [item.code for item in self.currencies]:
                default_currency = self.currencies[0].code if self.currencies else "IQD"
            self.currency = default_currency
            self.amount_field.text = ""
            self.debt_date_field.text = today_iso()
            self.due_date_field.text = ""
            self.notes_field.text = ""
        self._update_currency_button()

    # -- currency selection ---------------------------------------------
    def _update_currency_button(self) -> None:
        self.currency_button.text = T(f"العملة: {self.currency}")

    def _open_currency_menu(self) -> None:
        items = []
        for currency in self.currencies:
            items.append(
                {
                    "text": T(f"{currency.code} - {currency.name_ar}"),
                    "viewclass": "OneLineListItem",
                    "on_release": lambda *_, code=currency.code: self._select_currency(code),
                }
            )
        if not items:
            return
        self._menu = MDDropdownMenu(
            caller=self.currency_button, items=items, width_mult=4
        )
        self._menu.open()

    def _select_currency(self, code: str) -> None:
        self.currency = code
        self._update_currency_button()
        if hasattr(self, "_menu"):
            self._menu.dismiss()

    # -- save ------------------------------------------------------------
    def _save(self) -> None:
        try:
            if self.debt_id:
                self.app.services.debts.update(
                    self.debt_id,
                    amount=self.amount_field.text,
                    currency=self.currency,
                    debt_date=self.debt_date_field.text,
                    due_date=self.due_date_field.text.strip(),
                    notes=self.notes_field.text,
                )
            else:
                self.app.services.debts.create(
                    self.debtor_id,
                    self.amount_field.text,
                    self.currency,
                    debt_date=self.debt_date_field.text,
                    due_date=self.due_date_field.text.strip() or None,
                    notes=self.notes_field.text,
                )
        except Exception as exc:
            self.handle_error(exc)
            return
        self.app.back()
