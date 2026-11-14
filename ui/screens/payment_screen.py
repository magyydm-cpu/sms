"""Record a payment screen."""
from __future__ import annotations

from kivy.metrics import dp

from core import money
from core.time_utils import today_iso
from ui.screens.base import BaseScreen
from ui.widgets import ArLabel, make_button, make_field, make_scroll


class PaymentScreen(BaseScreen):
    screen_name = "payment"
    screen_title = "إضافة دفعة"

    def build(self) -> None:
        self.debt_id = None
        self.add_top_bar("إضافة دفعة", actions=[["content-save", lambda *_: self._save()]])
        scroll, self.box = make_scroll(padding_bottom=dp(24))
        self.content.add_widget(scroll)

        self.remaining_label = ArLabel(
            text="", font_size="15sp", bold=True, size_hint_y=None, height=dp(34)
        )
        self.amount_field = make_field("المبلغ المدفوع")
        self.date_field = make_field("تاريخ الدفع (YYYY-MM-DD)")
        self.receipt_field = make_field("رقم الإيصال - اختياري (يُولّد تلقائياً)")
        self.notes_field = make_field("ملاحظات", multiline=True, preview=True)

        self.box.add_widget(self.remaining_label)
        self.box.add_widget(self.amount_field)
        self.box.add_widget(self.date_field)
        self.box.add_widget(self.receipt_field)
        self.box.add_widget(self.notes_field)
        self.box.add_widget(make_button("تسجيل الدفعة", self._save))

    def load(self, debt_id=None, **kwargs) -> None:
        self.debt_id = debt_id

    def refresh(self) -> None:
        if not self.debt_id or not hasattr(self, "amount_field"):
            return
        try:
            summary = self.app.services.debts.overview(self.debt_id)
        except Exception as exc:
            self.handle_error(exc)
            return
        currency = summary.debt.currency
        self.remaining_label.set_text(
            f"المتبقي على الدين: {money.format_money(summary.remaining, currency)}"
        )
        self.amount_field.text = money.format_amount(summary.remaining, currency, grouping=False)
        self.date_field.text = today_iso()
        self.receipt_field.text = ""
        self.notes_field.text = ""

    def _save(self) -> None:
        try:
            self.app.services.payments.add(
                self.debt_id,
                self.amount_field.text,
                paid_at=self.date_field.text.strip() or None,
                notes=self.notes_field.text,
                receipt_no=self.receipt_field.text.strip() or None,
            )
        except Exception as exc:
            self.handle_error(exc)
            return
        self.app.back()
