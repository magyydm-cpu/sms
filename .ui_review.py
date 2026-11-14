"""Temporary UI review driver (Xvfb + Kivy) - not part of the app."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "artifacts", "ui")
DB_PATH = os.path.join(ROOT, "artifacts", "ui_demo.db")
os.makedirs(OUT, exist_ok=True)
for path in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"):
    if os.path.exists(path):
        os.remove(path)
os.environ["DEBT_MANAGER_DB"] = DB_PATH

from database.db import Database  # noqa: E402
from database.migrations import apply_migrations  # noqa: E402
from services import Services  # noqa: E402

# Import main (which sets the Kivy window size) before touching kivy modules,
# so the review runs at the phone-sized viewport used by the app.
from main import DebtManagerApp  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402


def seed() -> dict:
    db = Database(DB_PATH)
    apply_migrations(db)
    services = Services(db)
    ahmed = services.debtors.create("أحمد عبد الله", "+964 770 123 4567", "عميل منذ 2024")
    noor = services.debtors.create("شركة النور للتجارة", "0770 555 1122", "دفعات شهرية")
    services.debtors.create("سارة محمد", "٠٧٧٠ ٩٩٨ ٨٨٧٧")

    personal = services.debts.create(
        ahmed.id, "1250.00", "USD", "2026-01-10", "2026-03-01", "قرض شخصي"
    )
    services.payments.add(personal.id, "400.00", notes="دفعة أولى")
    services.installments.plan(personal.id, 3, "2026-11-01")

    local = services.debts.create(
        ahmed.id, "500000", "IQD", "2026-02-01", "2026-04-01", "بضاعة"
    )
    services.payments.add(local.id, "150000", notes="دفعة جزئية")

    company = services.debts.create(
        noor.id, "89.999", "KWD", "2026-02-10", "2026-03-10", "عقد صيانة"
    )
    services.payments.add(company.id, "9.999")

    old = services.debts.create(noor.id, "300.00", "USD", "2025-05-01")
    services.payments.add(old.id, "300.00", notes="سداد كامل")

    ids = {
        "ahmed": ahmed.id,
        "noor": noor.id,
        "personal": personal.id,
        "company": company.id,
    }
    db.close()
    return ids


IDS = seed()


class ReviewApp(DebtManagerApp):
    def on_start(self):
        self.checks: list[str] = []
        Clock.schedule_once(self.step_debtors, 1.2)

    def snap(self, name):
        path = os.path.join(OUT, name + ".png")
        Window.screenshot(name=path)
        print(f"SNAP {name} title={self.title!r} size={Window.size}", flush=True)

    def check(self, expected):
        actual = self.sm.current
        ok = actual == expected
        self.checks.append(f"{expected}:{'OK' if ok else 'FAIL(' + str(actual) + ')'}")
        print("CHECK", self.checks[-1], flush=True)

    def step_debtors(self, *_):
        self.check("debtors")
        self.snap("01_debtors")
        self.go("debtor_detail", debtor_id=IDS["ahmed"])
        Clock.schedule_once(self.step_debtor_detail, 1.0)

    def step_debtor_detail(self, *_):
        self.check("debtor_detail")
        self.snap("02_debtor_detail")
        self.go("debt_form", debtor_id=IDS["ahmed"])
        Clock.schedule_once(self.step_debt_form, 1.0)

    def step_debt_form(self, *_):
        self.check("debt_form")
        self.snap("03_debt_form")
        self.go("debt_detail", debt_id=IDS["personal"])
        Clock.schedule_once(self.step_debt_detail, 1.0)

    def step_debt_detail(self, *_):
        self.check("debt_detail")
        self.snap("04_debt_detail")
        self.go("payment", debt_id=IDS["personal"])
        Clock.schedule_once(self.step_payment, 1.0)

    def step_payment(self, *_):
        self.check("payment")
        self.snap("05_payment")
        self.go("installment_plan", debt_id=IDS["company"])
        Clock.schedule_once(self.step_plan, 1.0)

    def step_plan(self, *_):
        self.check("installment_plan")
        self.snap("06_installment_plan")
        self.go("debtor_form")
        Clock.schedule_once(self.step_debtor_form, 1.0)

    def step_debtor_form(self, *_):
        self.check("debtor_form")
        self.snap("07_debtor_form")
        screen = self.sm.get_screen("debtor_form")
        screen.name_field.text = "أحمد عبد الله"
        screen.phone_field.text = "+964 770 123 4567"
        screen.notes_field.text = "ملاحظة تجريبية"
        Clock.schedule_once(self.step_arabic_input, 1.0)

    def step_arabic_input(self, *_):
        screen = self.sm.get_screen("debtor_form")
        print(
            "ARABIC_INPUT name=", repr(screen.name_field.field.text),
            "notes=", repr(screen.notes_field.field.text),
            flush=True,
        )
        self.snap("08_debtor_form_arabic")
        # back-navigation check
        self.go("debtors")
        self.check("debtors")
        self.back()
        self.check("debtor_form")
        print("FLOW", " | ".join(self.checks), flush=True)
        Clock.schedule_once(lambda *_: self.stop(), 1.0)


if __name__ == "__main__":
    ReviewApp().run()
