"""Debtors list screen."""
from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFloatingActionButton

from ui.screens.base import BaseScreen
from ui.widgets import (
    ArLabel,
    ClickableCard,
    RTLBoxLayout,
    empty_label,
    icon_button,
    make_field,
    make_scroll,
    totals_lines,
)


class DebtorsScreen(BaseScreen):
    screen_name = "debtors"
    screen_title = "المدينون"

    def build(self) -> None:
        self.add_top_bar("المدينون", on_back=False)
        search_wrap = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(112),
            padding=[dp(12), dp(2), dp(12), dp(4)],
        )
        self.search_field = make_field("بحث بالاسم أو رقم الهاتف")
        self.search_field.bind(text=lambda *_: self.refresh())
        search_wrap.add_widget(self.search_field)
        self.content.add_widget(search_wrap)

        scroll, self.list_box = make_scroll()
        self.content.add_widget(scroll)

        self.fab = MDFloatingActionButton(
            icon="account-plus",
            pos_hint={"center_x": 0.13, "center_y": 0.08},
            on_release=lambda *_: self.app.go("debtor_form"),
        )
        self.add_widget(self.fab)

    def refresh(self) -> None:
        if not hasattr(self, "list_box"):
            return
        query = self.search_field.text if hasattr(self, "search_field") else ""
        try:
            items = self.app.services.debtors.list(query)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.handle_error(exc)
            return
        self.list_box.clear_widgets()
        if not items:
            self.list_box.add_widget(
                empty_label("لا يوجد مدينون مطابقون. أضف مديناً جديداً بزر +")
            )
            return
        for item in items:
            self.list_box.add_widget(self._debtor_card(item))

    def _debtor_card(self, item):
        debtor = item.debtor
        card = ClickableCard(
            on_click=lambda: self.app.go("debtor_detail", debtor_id=debtor.id),
            orientation="vertical",
            size_hint_y=None,
            height=dp(120),
            padding=[dp(12), dp(10), dp(12), dp(8)],
            spacing=dp(2),
            radius=[dp(14)],
            elevation=1,
        )
        head = RTLBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(4)
        )
        head.add_widget(ArLabel(text=debtor.name, font_size="17sp", bold=True))
        head.add_widget(
            icon_button(
                "chevron-left",
                lambda: self.app.go("debtor_detail", debtor_id=debtor.id),
            )
        )
        card.add_widget(head)
        card.add_widget(
            ArLabel(
                text=debtor.phone,
                font_size="13sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(22),
            )
        )
        card.add_widget(
            ArLabel(
                text=totals_lines(item.totals),
                font_size="14sp",
                size_hint_y=None,
                height=dp(24),
            )
        )
        card.add_widget(
            ArLabel(
                text=f"الديون: {item.debt_count} | غير مسددة: {item.open_debt_count}",
                font_size="12sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(20),
            )
        )
        return card
