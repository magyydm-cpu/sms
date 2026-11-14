"""Service-layer exceptions (separate from lower-level validation errors)."""
from __future__ import annotations


class ServiceError(Exception):
    """Base class for business errors that the UI can show to the user."""


class NotFoundError(ServiceError):
    def __init__(self, entity: str = "العنصر"):
        super().__init__(f"{entity} غير موجود أو تم حذفه")
        self.entity = entity


class BusinessRuleError(ServiceError):
    """A valid-looking request that violates a business rule."""


class DuplicateDebtorError(ServiceError):
    def __init__(self, existing, message: str | None = None):
        self.existing = existing
        name = getattr(existing, "name", "")
        phone = getattr(existing, "phone", "")
        super().__init__(message or f"يوجد مدين مسجل بنفس رقم الهاتف: {name} ({phone})")
