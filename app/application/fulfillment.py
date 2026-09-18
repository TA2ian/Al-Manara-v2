from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FulfillmentResult:
    internal_order_id: UUID
    public_order_code: str
    status: str
    version: int
    admin_telegram_user_id: int
    occurred_at: datetime
    replayed: bool


class FulfillmentRepository(Protocol):
    async def claim(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        session_id: UUID,
    ) -> FulfillmentResult: ...

    async def complete(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        session_id: UUID,
        manual_usdt_transfer_reference: str,
    ) -> FulfillmentResult: ...


class FulfillmentService:
    """Application boundary for the operational fulfillment lifecycle."""

    def __init__(self, repository: FulfillmentRepository) -> None:
        self._repository = repository

    async def claim(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        session_id: UUID,
    ) -> FulfillmentResult:
        actor, key, session = self._validate(
            internal_order_id, expected_version, admin_telegram_user_id, actor_type, idempotency_key, session_id
        )
        return await self._repository.claim(
            internal_order_id, expected_version, admin_telegram_user_id, actor, key, session
        )

    async def complete(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        session_id: UUID,
        manual_usdt_transfer_reference: str,
    ) -> FulfillmentResult:
        actor, key, session = self._validate(
            internal_order_id, expected_version, admin_telegram_user_id, actor_type, idempotency_key, session_id
        )
        reference = self._validate_transfer_reference(manual_usdt_transfer_reference)
        return await self._repository.complete(
            internal_order_id, expected_version, admin_telegram_user_id, actor, key, session, reference
        )

    @staticmethod
    def _validate_transfer_reference(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("manual USDT transfer reference is required")
        reference = value.strip()
        if not 1 <= len(reference) <= 200:
            raise ValueError("manual USDT transfer reference must be between 1 and 200 characters")
        return reference

    @staticmethod
    def _validate(
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        session_id: UUID,
    ) -> tuple[str, str, UUID]:
        if not isinstance(internal_order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(expected_version, int) or expected_version < 1:
            raise ValueError("expected version must be positive")
        if not isinstance(admin_telegram_user_id, int) or admin_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        if not isinstance(actor_type, str):
            raise ValueError("admin actor type is required")
        actor = actor_type.strip().lower()
        if actor not in {"primary", "backup"}:
            raise ValueError("unsupported admin actor type")
        if not isinstance(idempotency_key, str):
            raise ValueError("idempotency key is required")
        key = idempotency_key.strip()
        if not 1 <= len(key) <= 128:
            raise ValueError("idempotency key must be between 1 and 128 characters")
        if not isinstance(session_id, UUID):
            raise ValueError("recent admin session is required")
        return actor, key, session_id
