"""Installment plan creation screen."""
from __future__ import annotations

from kivy.metrics import dp

from core import calculations, money, validation
from core.time_utils import format_date_display, today
from ui.arabic import ltr
from ui.screens.base import BaseScreen
from ui.widgets import ArLabel, make_button, make_field, make_scroll


class InstallmentPlanScreen(BaseScreen):
    screen_name = "installment_plan"
    screen_title = "تقسيم الدين إلى أقساط"

    def build(self) -> None:
        self.debt_id = None
        self.add_top_bar(
            "تقسيم الدين إلى أقساط", actions=[["content-save", lambda *_: self._save()]]
        )
        scroll, self.box = make_scroll(padding_bottom=dp(24))
        self.content.add_widget(scroll)

        self.remaining_label = ArLabel(
            text="", font_size="15sp", bold=True, size_hint_y=None, height=dp(34)
        )
        self.count_field = make_field("عدد الأقساط")
        self.first_due_field = make_field("تاريخ استحقاق القسط الأول (YYYY-MM-DD)")
        self.months_field = make_field("الفاصل بين الأقساط بالأشهر")
        self.preview_label = ArLabel(
            text="",
            font_size="12sp",
            size_hint_y=None,
            height=dp(170),
            valign="top",
            theme_text_color="Secondary",
        )

        self.box.add_widget(self.remaining_label)
        self.box.add_widget(self.count_field)
        self.box.add_widget(self.first_due_field)
        self.box.add_widget(self.months_field)
        self.box.add_widget(self.preview_label)
        self.box.add_widget(make_button("إنشاء خطة الأقساط", self._save))

        for field in (self.count_field, self.first_due_field, self.months_field):
            field.bind(text=lambda *_: self._update_preview())

    def load(self, debt_id=None, **kwargs) -> None:
        self.debt_id = debt_id

    def refresh(self) -> None:
        if not self.debt_id or not hasattr(self, "count_field"):
            return
        try:
            summary = self.app.services.debts.overview(self.debt_id)
        except Exception as exc:
            self.handle_error(exc)
            return
        currency = summary.debt.currency
        self.remaining_label.set_text(
            f"المتبقي القابل للتقسيم: {money.format_money(summary.remaining, currency)}"
        )
        self.count_field.text = "3"
        first_due = calculations.add_months(today(), 1)
        self.first_due_field.text = first_due.isoformat()
        self.months_field.text = "1"
        self._update_preview()

    def _update_preview(self) -> None:
        if not self.debt_id or not hasattr(self, "preview_label"):
            return
        try:
            summary = self.app.services.debts.overview(self.debt_id)
            count = int(self.count_field.text.strip())
            months = int(self.months_field.text.strip())
            first_due = validation.parse_date(self.first_due_field.text, "first_due_date")
            parts = calculations.split_amount(summary.remaining, count, summary.debt.currency)
            dates = calculations.installment_due_dates(first_due, count, months)
            lines = []
            for index, (part, due) in enumerate(zip(parts, dates)):
                line = (
                    f"{index + 1}. {money.format_money(part, summary.debt.currency)} - "
                    f"{format_date_display(due)}"
                )
                lines.append(ltr(line))
            self.preview_label.set_text("معاينة الأقساط:\n" + "\n".join(lines))
        except Exception:
            self.preview_label.set_text(
                "أدخل عدد الأقساط وتاريخ الاستحقاق لعرض المعاينة"
            )

    def _save(self) -> None:
        try:
            self.app.services.installments.plan(
                self.debt_id,
                self.count_field.text,
                self.first_due_field.text,
                months_between=self.months_field.text,
            )
        except Exception as exc:
            self.handle_error(exc)
            return
        self.app.back()
