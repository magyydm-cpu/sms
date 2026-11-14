"""Business services package.

The UI only talks to these services; it never issues SQL.
"""
from __future__ import annotations

from database.db import Database
from services.debt_service import DebtService
from services.debtor_service import DebtorService
from services.errors import BusinessRuleError, DuplicateDebtorError, NotFoundError, ServiceError
from services.installment_service import InstallmentService
from services.payment_service import PaymentService
from services.reference_service import ReferenceService


class Services:
    def __init__(self, db: Database):
        self.db = db
        self.reference = ReferenceService(db)
        self.debtors = DebtorService(db)
        self.debts = DebtService(db)
        self.payments = PaymentService(db)
        self.installments = InstallmentService(db)


__all__ = [
    "Services",
    "ServiceError",
    "NotFoundError",
    "BusinessRuleError",
    "DuplicateDebtorError",
]
