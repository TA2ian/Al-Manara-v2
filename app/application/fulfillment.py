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
    ) -> FulfillmentResult: ...

    async def complete(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
    ) -> FulfillmentResult: ...


class FulfillmentService:
    """Application boundary for the operational fulfillment lifecycle."""

    def __init__(self, repository: FulfillmentRepository) -> None:
        self._repository = repository

    async def claim(self, internal_order_id: UUID, expected_version: int, admin_telegram_user_id: int, actor_type: str, idempotency_key: str) -> FulfillmentResult:
        actor, key = self._validate(internal_order_id, expected_version, admin_telegram_user_id, actor_type, idempotency_key)
        return await self._repository.claim(internal_order_id, expected_version, admin_telegram_user_id, actor, key)

    async def complete(self, internal_order_id: UUID, expected_version: int, admin_telegram_user_id: int, actor_type: str, idempotency_key: str) -> FulfillmentResult:
        actor, key = self._validate(internal_order_id, expected_version, admin_telegram_user_id, actor_type, idempotency_key)
        return await self._repository.complete(internal_order_id, expected_version, admin_telegram_user_id, actor, key)

    @staticmethod
    def _validate(internal_order_id: UUID, expected_version: int, admin_telegram_user_id: int, actor_type: str, idempotency_key: str) -> tuple[str, str]:
        if not isinstance(internal_order_id, UUID):
            raise ValueError("order id is required")
        if expected_version < 1:
            raise ValueError("expected version must be positive")
        if admin_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        actor = actor_type.strip().lower()
        if actor not in {"primary", "backup"}:
            raise ValueError("unsupported admin actor type")
        key = idempotency_key.strip()
        if not 1 <= len(key) <= 128:
            raise ValueError("idempotency key must be between 1 and 128 characters")
        return actor, key
