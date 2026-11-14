"""Debt Manager Pro - Android app entry point (Kivy + KivyMD)."""
from __future__ import annotations

import os

from kivy.config import Config

# Desktop-friendly window size; ignored on Android.
if not os.environ.get("ANDROID_PRIVATE"):
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "880")
Config.set("kivy", "exit_on_escape", "0")

from kivy.core.window import Window  # noqa: E402
from kivymd.app import MDApp  # noqa: E402
from kivymd.uix.screenmanager import MDScreenManager  # noqa: E402

from database.db import Database, default_db_path  # noqa: E402
from database.migrations import apply_migrations  # noqa: E402
from services import Services  # noqa: E402
from ui.arabic import register_fonts  # noqa: E402
from ui.screens.debt_detail_screen import DebtDetailScreen  # noqa: E402
from ui.screens.debt_form_screen import DebtFormScreen  # noqa: E402
from ui.screens.debtor_detail_screen import DebtorDetailScreen  # noqa: E402
from ui.screens.debtor_form_screen import DebtorFormScreen  # noqa: E402
from ui.screens.debtors_screen import DebtorsScreen  # noqa: E402
from ui.screens.installment_plan_screen import InstallmentPlanScreen  # noqa: E402
from ui.screens.payment_screen import PaymentScreen  # noqa: E402

SCREEN_CLASSES = (
    DebtorsScreen,
    DebtorDetailScreen,
    DebtorFormScreen,
    DebtFormScreen,
    DebtDetailScreen,
    PaymentScreen,
    InstallmentPlanScreen,
)


class DebtManagerApp(MDApp):
    title = "مدير الديون والتحصيل الذكي"
    name = "debtmanagerpro"

    def build(self):
        register_fonts()
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.material_style = "M3"
        Window.softinput_mode = "below_target"

        # An explicit DB path (tests/backup restores) must not require Kivy to
        # create its desktop data directory first.
        db_path = os.environ.get("DEBT_MANAGER_DB") or default_db_path(self.user_data_dir)
        self.db = Database(db_path)
        apply_migrations(self.db)
        self.services = Services(self.db)
        self.history: list[str] = []

        self.sm = MDScreenManager()
        for screen_class in SCREEN_CLASSES:
            self.sm.add_widget(screen_class(self))
        Window.bind(on_keyboard=self._on_keyboard)
        return self.sm

    # -- navigation ------------------------------------------------------
    def go(self, name: str, **kwargs) -> None:
        if self.sm.current:
            self.history.append(self.sm.current)
        screen = self.sm.get_screen(name)
        screen.load(**kwargs)
        self.sm.current = name

    def back(self) -> None:
        if self.history:
            self.sm.current = self.history.pop()
            return
        if self.sm.current != "debtors":
            self.sm.current = "debtors"

    def _on_keyboard(self, _window, key, *_args):
        if key == 27:  # Android back button / Escape
            if self.history or self.sm.current != "debtors":
                self.back()
                return True
        return False

    def on_stop(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass


if __name__ == "__main__":
    DebtManagerApp().run()
