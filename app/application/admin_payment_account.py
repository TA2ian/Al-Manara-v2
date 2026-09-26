from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


@dataclass(frozen=True, slots=True)
class AdminPaymentAccount:
    id: str
    currency: CurrencyCode
    account_name: str
    account_number: str
    qr_image_file_id: str
    is_active: bool
    updated_at: datetime


class AdminPaymentAccountRepository(Protocol):
    async def create_confirmation(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID, operation: str, request_fingerprint: str) -> UUID: ...
    async def list(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> list[AdminPaymentAccount]: ...
    async def upsert(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, setup: PaymentMethodSetup, session_id: UUID, confirmation_id: UUID, request_fingerprint: str) -> AdminPaymentAccount: ...
    async def set_active(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, is_active: bool, session_id: UUID, confirmation_id: UUID, request_fingerprint: str) -> AdminPaymentAccount: ...


class AdminPaymentAccountService:
    """Application boundary for security-sensitive ShamCash receiving-account management."""

    UPSERT_OPERATION = "admin_payment_account.upsert"
    STATUS_OPERATION = "admin_payment_account.status"

    def __init__(self, repository: AdminPaymentAccountRepository, *, emergency_mode: bool = False) -> None:
        self._repository = repository
        self._emergency_mode = emergency_mode

    def _ensure_allowed(self, actor_type: str) -> str:
        normalized = actor_type.strip().lower() if isinstance(actor_type, str) else ""
        if normalized not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if normalized == "backup" and not self._emergency_mode:
            raise PermissionError("backup administrator requires emergency mode")
        return normalized

    @staticmethod
    def _validate_admin(admin_telegram_user_id: int, actor_type: str) -> str:
        if not isinstance(admin_telegram_user_id, int) or admin_telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        if not isinstance(actor_type, str):
            raise ValueError("administrator actor type is required")
        normalized = actor_type.strip().lower()
        if normalized not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        return normalized

    @staticmethod
    def _validate_session(session_id: UUID) -> None:
        if not isinstance(session_id, UUID):
            raise ValueError("administrator session is required")

    @staticmethod
    def _fingerprint(operation: str, payload: dict[str, object]) -> str:
        canonical = json.dumps({"operation": operation, "payload": payload}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    async def request_upsert_confirmation(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, setup: PaymentMethodSetup, session_id: UUID) -> UUID:
        normalized_actor = self._ensure_allowed(actor_type)
        self._validate_admin(admin_telegram_user_id, normalized_actor)
        self._validate_session(session_id)
        if not isinstance(currency, CurrencyCode) or not isinstance(setup, PaymentMethodSetup):
            raise ValueError("valid payment setup is required")
        fingerprint = self._fingerprint(self.UPSERT_OPERATION, {"currency": currency.value, "account_name": setup.recipient_name, "account_number": setup.receiving_address, "qr_image_file_id": setup.qr_image_file_id})
        return await self._repository.create_confirmation(admin_telegram_user_id, normalized_actor, session_id, self.UPSERT_OPERATION, fingerprint)

    async def request_set_active_confirmation(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, is_active: bool, session_id: UUID) -> UUID:
        normalized_actor = self._ensure_allowed(actor_type)
        self._validate_admin(admin_telegram_user_id, normalized_actor)
        self._validate_session(session_id)
        if not isinstance(currency, CurrencyCode) or not isinstance(is_active, bool):
            raise ValueError("valid payment status is required")
        fingerprint = self._fingerprint(self.STATUS_OPERATION, {"currency": currency.value, "is_active": is_active})
        return await self._repository.create_confirmation(admin_telegram_user_id, normalized_actor, session_id, self.STATUS_OPERATION, fingerprint)

    async def list(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> list[AdminPaymentAccount]:
        normalized_actor = self._ensure_allowed(actor_type)
        self._validate_admin(admin_telegram_user_id, normalized_actor)
        self._validate_session(session_id)
        return await self._repository.list(admin_telegram_user_id, normalized_actor, session_id)

    async def upsert(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, setup: PaymentMethodSetup, session_id: UUID, confirmation_id: UUID) -> AdminPaymentAccount:
        normalized_actor = self._ensure_allowed(actor_type)
        self._validate_admin(admin_telegram_user_id, normalized_actor)
        self._validate_session(session_id)
        if not isinstance(currency, CurrencyCode) or not isinstance(setup, PaymentMethodSetup) or not isinstance(confirmation_id, UUID):
            raise ValueError("valid payment mutation input is required")
        fingerprint = self._fingerprint(self.UPSERT_OPERATION, {"currency": currency.value, "account_name": setup.recipient_name, "account_number": setup.receiving_address, "qr_image_file_id": setup.qr_image_file_id})
        return await self._repository.upsert(admin_telegram_user_id, normalized_actor, currency, setup, session_id, confirmation_id, fingerprint)

    async def set_active(self, admin_telegram_user_id: int, actor_type: str, currency: CurrencyCode, is_active: bool, session_id: UUID, confirmation_id: UUID) -> AdminPaymentAccount:
        normalized_actor = self._ensure_allowed(actor_type)
        self._validate_admin(admin_telegram_user_id, normalized_actor)
        self._validate_session(session_id)
        if not isinstance(currency, CurrencyCode) or not isinstance(is_active, bool) or not isinstance(confirmation_id, UUID):
            raise ValueError("valid payment status mutation input is required")
        fingerprint = self._fingerprint(self.STATUS_OPERATION, {"currency": currency.value, "is_active": is_active})
        return await self._repository.set_active(admin_telegram_user_id, normalized_actor, currency, is_active, session_id, confirmation_id, fingerprint)
