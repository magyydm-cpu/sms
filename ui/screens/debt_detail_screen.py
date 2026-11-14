"""Debt detail screen: summary, installments and payments log."""
from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.card import MDCard

from core import money
from ui.arabic import ltr
from ui.screens.base import BaseScreen
from ui.widgets import (
    ArLabel,
    DANGER,
    RTLBoxLayout,
    SUCCESS,
    confirm,
    empty_label,
    icon_button,
    info_row,
    make_button,
    make_scroll,
    section_title,
    status_chip,
)


class DebtDetailScreen(BaseScreen):
    screen_name = "debt_detail"
    screen_title = "تفاصيل الدين"

    def build(self) -> None:
        self.debt_id = None
        self.add_top_bar(
            "تفاصيل الدين",
            actions=[
                ["pencil", lambda *_: self._edit()],
                ["trash-can-outline", lambda *_: self._delete()],
            ],
        )
        scroll, self.box = make_scroll()
        self.content.add_widget(scroll)

    def load(self, debt_id=None, **kwargs) -> None:
        self.debt_id = debt_id

    def refresh(self) -> None:
        if not self.debt_id or not hasattr(self, "box"):
            return
        try:
            summary = self.app.services.debts.overview(self.debt_id)
            payments = self.app.services.payments.list_for_debt(self.debt_id)
            installments = self.app.services.installments.list_for_debt(self.debt_id)
            debtor = self.app.services.debtors.get(summary.debt.debtor_id)
        except Exception as exc:
            self.handle_error(exc)
            return
        self.summary = summary
        self.box.clear_widgets()
        currency = summary.debt.currency

        card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(238) if summary.debt.notes else dp(206),
            padding=[dp(14), dp(10)],
            spacing=dp(2),
            radius=[dp(14)],
            elevation=1,
        )
        head = RTLBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(4)
        )
        head.add_widget(
            ArLabel(
                text=money.format_money(summary.total, currency),
                font_size="20sp",
                bold=True,
            )
        )
        head.add_widget(status_chip(summary.status_label, summary.status))
        card.add_widget(head)
        card.add_widget(
            ArLabel(
                text=f"المدين: {debtor.name} - {ltr(debtor.original_phone)}",
                font_size="13sp",
                size_hint_y=None,
                height=dp(24),
            )
        )
        card.add_widget(info_row("تاريخ الدين", summary.debt.debt_date_display))
        card.add_widget(info_row("الاستحقاق", summary.debt.due_date_display or "غير محدد"))
        card.add_widget(info_row("المدفوع", money.format_money(summary.paid, currency), SUCCESS))
        card.add_widget(
            info_row(
                "المتبقي",
                money.format_money(summary.remaining, currency),
                SUCCESS if summary.is_paid else DANGER,
            )
        )
        if summary.debt.notes:
            card.add_widget(
                ArLabel(
                    text=summary.debt.notes,
                    font_size="13sp",
                    size_hint_y=None,
                    height=dp(32),
                )
            )
        self.box.add_widget(card)

        if not summary.is_paid:
            self.box.add_widget(make_button("إضافة دفعة", self._add_payment))
            if not installments:
                self.box.add_widget(
                    make_button("تقسيم المتبقي إلى أقساط", self._plan_installments)
                )

        self.box.add_widget(section_title(f"سجل الدفعات ({len(payments)})"))
        if not payments:
            self.box.add_widget(empty_label("لا توجد دفعات مسجلة بعد"))
        else:
            for payment in payments:
                self.box.add_widget(self._payment_row(payment))

        if installments:
            self.box.add_widget(section_title(f"خطة الأقساط ({len(installments)})"))
            for view in installments:
                self.box.add_widget(self._installment_row(view))
            paid_any = any(
                view.installment.status == "paid" for view in installments
            )
            if not paid_any:
                self.box.add_widget(
                    make_button(
                        "حذف خطة الأقساط",
                        self._delete_plan,
                        md_bg_color=DANGER,
                    )
                )

    # -- rows ------------------------------------------------------------
    def _payment_row(self, payment):
        row = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(92) if payment.notes else dp(70),
            padding=[dp(12), dp(6)],
            spacing=dp(2),
            radius=[dp(12)],
            elevation=0,
        )
        top = RTLBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(4)
        )
        top.add_widget(
            ArLabel(
                text=money.format_money(payment.amount, payment.currency),
                font_size="15sp",
                bold=True,
            )
        )
        top.add_widget(
            ArLabel(
                text=f"إيصال {payment.receipt_no}",
                font_size="12sp",
                theme_text_color="Secondary",
            )
        )
        row.add_widget(top)
        row.add_widget(
            ArLabel(
                text=payment.paid_at_display,
                font_size="12sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(20),
            )
        )
        if payment.notes:
            row.add_widget(
                ArLabel(text=payment.notes, font_size="12sp", size_hint_y=None, height=dp(22))
            )
        return row

    def _installment_row(self, view):
        card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(108),
            padding=[dp(10), dp(6)],
            spacing=dp(2),
            radius=[dp(12)],
            elevation=0,
        )
        top = RTLBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(4)
        )
        top.add_widget(
            ArLabel(text=f"القسط {view.installment.seq}", font_size="14sp", bold=True)
        )
        top.add_widget(status_chip(view.status_label, view.effective_status))
        if view.is_payable:
            top.add_widget(
                icon_button("cash-check", lambda view=view: self._pay_installment(view))
            )
        card.add_widget(top)
        card.add_widget(info_row("المبلغ", view.amount_display))
        card.add_widget(info_row("تاريخ الاستحقاق", view.installment.due_date_display))
        return card

    # -- actions ---------------------------------------------------------
    def _add_payment(self) -> None:
        if self.debt_id:
            self.app.go("payment", debt_id=self.debt_id)

    def _plan_installments(self) -> None:
        if self.debt_id:
            self.app.go("installment_plan", debt_id=self.debt_id)

    def _pay_installment(self, view) -> None:
        def _confirmed():
            try:
                payment = self.app.services.installments.pay(view.installment.id)
            except Exception as exc:
                self.handle_error(exc)
                return
            self.refresh()
            self.notify(f"تم تسجيل الدفعة بإيصال {payment.receipt_no}")

        confirm(
            "سداد القسط",
            f"سيتم تسجيل دفعة بمبلغ {view.amount_display} للقسط رقم "
            f"{view.installment.seq}. هل تريد المتابعة؟",
            _confirmed,
            confirm_text="سداد",
        )

    def _delete_plan(self) -> None:
        def _confirmed():
            try:
                self.app.services.installments.delete_plan(self.debt_id)
            except Exception as exc:
                self.handle_error(exc)
                return
            self.refresh()

        confirm(
            "حذف خطة الأقساط",
            "سيتم حذف جميع الأقساط غير المسددة لهذا الدين. هل تريد المتابعة؟",
            _confirmed,
            confirm_text="حذف",
        )

    def _edit(self) -> None:
        if self.debt_id and getattr(self, "summary", None):
            self.app.go(
                "debt_form",
                debtor_id=self.summary.debt.debtor_id,
                debt_id=self.debt_id,
            )

    def _delete(self) -> None:
        if not self.debt_id:
            return

        def _confirmed():
            try:
                self.app.services.debts.delete(self.debt_id)
            except Exception as exc:
                self.handle_error(exc)
                return
            self.debt_id = None
            self.app.back()

        confirm(
            "حذف الدين",
            "سيتم حذف الدين وجميع دفعاته وأقساطه نهائياً (مع حفظ نسخة في سجل التدقيق). "
            "هل أنت متأكد؟",
            _confirmed,
            confirm_text="حذف",
        )
