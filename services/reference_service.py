"""Read-only reference data: currencies and app settings."""
from __future__ import annotations

from database.dao import CurrencyDAO
from database.db import Database
from database.models import Currency


class ReferenceService:
    def __init__(self, db: Database):
        self.db = db

    def currencies(self) -> list[Currency]:
        with self.db.transaction() as conn:
            return CurrencyDAO(conn).list_active()

    def currency(self, code: str) -> Currency | None:
        with self.db.transaction() as conn:
            return CurrencyDAO(conn).get(code)

    def currency_codes(self) -> list[str]:
        with self.db.transaction() as conn:
            return CurrencyDAO(conn).codes()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def default_currency(self) -> str:
        return self.get_setting("default_currency", "IQD") or "IQD"
