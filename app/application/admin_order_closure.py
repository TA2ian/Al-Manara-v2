from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class AdminOrderClosureCommand:
    internal_order_id: UUID
    admin_telegram_user_id: int
    expected_version: int
    session_id: UUID
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AdminOrderClosureResult:
    internal_order_id: UUID
    public_order_code: str
    status: str
    version: int
    replayed: bool


class AdminOrderClosureRepository(Protocol):
    async def close_without_fulfillment(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        session_id: UUID,
        reason: str,
        idempotency_key: str,
    ) -> AdminOrderClosureResult: ...


class AdminOrderClosureService:
    """Application boundary for the privileged closure path."""

    def __init__(self, repository: AdminOrderClosureRepository) -> None:
        self._repository = repository

    async def close_without_fulfillment(
        self, command: AdminOrderClosureCommand
    ) -> AdminOrderClosureResult:
        if command.admin_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        if command.expected_version < 1:
            raise ValueError("expected version must be positive")
        reason = " ".join(command.reason.split())
        if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
            raise ValueError(
                f"closure reason must be between {MIN_REASON_LENGTH} and {MAX_REASON_LENGTH} characters"
            )
        idempotency_key = command.idempotency_key.strip()
        if not 1 <= len(idempotency_key) <= 128:
            raise ValueError("idempotency key must be between 1 and 128 characters")

        return await self._repository.close_without_fulfillment(
            command.internal_order_id,
            command.expected_version,
            command.admin_telegram_user_id,
            command.session_id,
            reason,
            idempotency_key,
        )
