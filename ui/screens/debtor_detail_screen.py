"""Debtor detail screen."""
from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.button import MDFloatingActionButton
from kivymd.uix.card import MDCard

from core import money
from core.time_utils import format_date_display
from ui.screens.base import BaseScreen
from ui.widgets import (
    ArLabel,
    DANGER,
    ClickableCard,
    RTLBoxLayout,
    SUCCESS,
    confirm,
    empty_label,
    info_row,
    make_scroll,
    section_title,
    status_chip,
)


class DebtorDetailScreen(BaseScreen):
    screen_name = "debtor_detail"
    screen_title = "تفاصيل المدين"

    def build(self) -> None:
        self.debtor_id = None
        self.add_top_bar(
            "تفاصيل المدين",
            actions=[
                ["pencil", lambda *_: self._edit()],
                ["trash-can-outline", lambda *_: self._delete()],
            ],
        )
        scroll, self.box = make_scroll()
        self.content.add_widget(scroll)
        self.add_widget(
            MDFloatingActionButton(
                icon="plus",
                pos_hint={"center_x": 0.13, "center_y": 0.08},
                on_release=lambda *_: self._add_debt(),
            )
        )

    def load(self, debtor_id=None, **kwargs) -> None:
        self.debtor_id = debtor_id

    def refresh(self) -> None:
        if not self.debtor_id or not hasattr(self, "box"):
            return
        try:
            summary = self.app.services.debtors.overview(self.debtor_id)
        except Exception as exc:
            self.handle_error(exc)
            return
        self.box.clear_widgets()
        debtor = summary.debtor

        profile = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(150) if debtor.notes else dp(120),
            padding=[dp(14), dp(10)],
            spacing=dp(2),
            radius=[dp(14)],
            elevation=1,
        )
        profile.add_widget(ArLabel(text=debtor.name, font_size="19sp", bold=True))
        profile.add_widget(
            ArLabel(text=debtor.original_phone, font_size="14sp", size_hint_y=None, height=dp(24))
        )
        profile.add_widget(
            ArLabel(
                text=f"تاريخ الإضافة: {format_date_display(debtor.created_at)}",
                font_size="12sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(22),
            )
        )
        if debtor.notes:
            profile.add_widget(
                ArLabel(text=debtor.notes, font_size="13sp", size_hint_y=None, height=dp(40))
            )
        self.box.add_widget(profile)

        if summary.totals:
            totals_card = MDCard(
                orientation="vertical",
                size_hint_y=None,
                # padding (16) + section title (32) + three rows per currency (28 each)
                height=dp(16 + 32 + 28 * 3 * len(summary.totals)),
                padding=[dp(14), dp(8)],
                spacing=dp(2),
                radius=[dp(14)],
                elevation=1,
            )
            totals_card.add_widget(section_title("الإجماليات حسب العملة"))
            for currency in sorted(summary.totals):
                bucket = summary.totals[currency]
                totals_card.add_widget(
                    info_row(f"إجمالي {currency}", money.format_amount(bucket["total"], currency))
                )
                totals_card.add_widget(
                    info_row("المدفوع", money.format_amount(bucket["paid"], currency), SUCCESS)
                )
                totals_card.add_widget(
                    info_row(
                        "المتبقي", money.format_amount(bucket["remaining"], currency), DANGER
                    )
                )
            self.box.add_widget(totals_card)

        self.box.add_widget(section_title(f"الديون ({summary.debt_count})"))
        if not summary.debts:
            self.box.add_widget(empty_label("لا توجد ديون لهذا المدين. أضف ديناً بزر +"))
        else:
            for item in summary.debts:
                self.box.add_widget(self._debt_card(item))

    def _debt_card(self, item):
        currency = item.debt.currency
        card = ClickableCard(
            on_click=lambda: self.app.go("debt_detail", debt_id=item.debt.id),
            orientation="vertical",
            size_hint_y=None,
            height=dp(200) if item.installments_total else dp(174),
            padding=[dp(12), dp(8)],
            spacing=dp(2),
            radius=[dp(14)],
            elevation=1,
        )
        head = RTLBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(4)
        )
        head.add_widget(
            ArLabel(text=money.format_money(item.total, currency), font_size="17sp", bold=True)
        )
        head.add_widget(status_chip(item.status_label, item.status))
        card.add_widget(head)
        card.add_widget(info_row("تاريخ الدين", item.debt.debt_date_display))
        card.add_widget(info_row("تاريخ الاستحقاق", item.debt.due_date_display or "غير محدد"))
        card.add_widget(info_row("المدفوع", money.format_money(item.paid, currency), SUCCESS))
        card.add_widget(
            info_row(
                "المتبقي",
                money.format_money(item.remaining, currency),
                SUCCESS if item.is_paid else DANGER,
            )
        )
        if item.installments_total:
            card.add_widget(
                info_row(
                    "خطة الأقساط",
                    f"{item.installments_paid}/{item.installments_total}"
                    + (f" (متأخر: {item.installments_overdue})" if item.installments_overdue else ""),
                )
            )
        return card

    # -- actions ---------------------------------------------------------
    def _edit(self) -> None:
        if self.debtor_id:
            self.app.go("debtor_form", debtor_id=self.debtor_id)

    def _delete(self) -> None:
        if not self.debtor_id:
            return

        def _confirmed():
            try:
                self.app.services.debtors.delete(self.debtor_id)
            except Exception as exc:
                self.handle_error(exc)
                return
            self.debtor_id = None
            self.app.back()

        confirm(
            "حذف المدين",
            "سيتم حذف المدين وكل ديونه ودفعاته وأقساطه نهائياً. "
            "تُحفظ نسخة في سجل التدقيق. هل أنت متأكد؟",
            _confirmed,
            confirm_text="حذف",
        )

    def _add_debt(self) -> None:
        if self.debtor_id:
            self.app.go("debt_form", debtor_id=self.debtor_id)
