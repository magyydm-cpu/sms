"""Debtor add/edit form screen."""
from __future__ import annotations

from kivy.metrics import dp

from ui.screens.base import BaseScreen
from ui.widgets import ArLabel, make_button, make_field, make_scroll


class DebtorFormScreen(BaseScreen):
    screen_name = "debtor_form"
    screen_title = "بيانات المدين"

    def build(self) -> None:
        self.debtor_id = None
        self.add_top_bar(
            "بيانات المدين", actions=[["content-save", lambda *_: self._save()]]
        )
        scroll, self.box = make_scroll(padding_bottom=dp(24))
        self.content.add_widget(scroll)

        self.name_field = make_field("الاسم الكامل", preview=True)
        self.phone_field = make_field("رقم الهاتف (مثال: 07701234567 أو +9647701234567)")
        self.notes_field = make_field("ملاحظات", multiline=True, preview=True)

        self.box.add_widget(self.name_field)
        self.box.add_widget(self.phone_field)
        self.box.add_widget(
            ArLabel(
                text="يُحفظ الرقم كما أدخلته دون تغيير. تُنظَّف الأرقام للمقارنة فقط.",
                font_size="12sp",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(48),
            )
        )
        self.box.add_widget(self.notes_field)
        self.box.add_widget(make_button("حفظ", self._save))

    def load(self, debtor_id=None, **kwargs) -> None:
        self.debtor_id = debtor_id

    def refresh(self) -> None:
        if not hasattr(self, "name_field"):
            return
        if not self.debtor_id:
            self.name_field.text = ""
            self.phone_field.text = ""
            self.notes_field.text = ""
            return
        try:
            debtor = self.app.services.debtors.get(self.debtor_id)
        except Exception as exc:
            self.handle_error(exc)
            return
        self.name_field.text = debtor.name
        self.phone_field.text = debtor.original_phone
        self.notes_field.text = debtor.notes

    def _save(self) -> None:
        try:
            if self.debtor_id:
                self.app.services.debtors.update(
                    self.debtor_id,
                    self.name_field.text,
                    self.phone_field.text,
                    self.notes_field.text,
                )
            else:
                self.app.services.debtors.create(
                    self.name_field.text,
                    self.phone_field.text,
                    self.notes_field.text,
                )
        except Exception as exc:
            self.handle_error(exc)
            return
        self.app.back()
