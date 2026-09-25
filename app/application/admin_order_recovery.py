from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


MIN_REASON_LENGTH = 5
MAX_REASON_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class AdminOrderRecoveryCommand:
    internal_order_id: UUID
    admin_telegram_user_id: int
    actor_type: str
    expected_version: int
    session_id: UUID
    confirmation_id: UUID
    request_fingerprint: str
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AdminOrderRecoveryResult:
    internal_order_id: UUID
    public_order_code: str
    status: str
    version: int
    replayed: bool


class AdminOrderRecoveryRepository(Protocol):
    async def reopen_for_receipt(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
        reason: str,
        idempotency_key: str,
    ) -> AdminOrderRecoveryResult: ...


class AdminOrderRecoveryService:
    """Controlled recovery of a customer clarification back into human review."""

    def __init__(self, repository: AdminOrderRecoveryRepository) -> None:
        self._repository = repository

    async def reopen_for_receipt(self, command: AdminOrderRecoveryCommand) -> AdminOrderRecoveryResult:
        if not isinstance(command.internal_order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.admin_telegram_user_id, int) or command.admin_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        if command.actor_type not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if not isinstance(command.expected_version, int) or command.expected_version < 1:
            raise ValueError("expected version must be positive")
        if not isinstance(command.session_id, UUID) or not isinstance(command.confirmation_id, UUID):
            raise ValueError("admin session and confirmation are required")
        if not isinstance(command.request_fingerprint, str) or len(command.request_fingerprint) != 64:
            raise ValueError("invalid request fingerprint")
        if not isinstance(command.reason, str):
            raise ValueError("recovery reason is required")
        reason = " ".join(command.reason.split())
        if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
            raise ValueError("recovery reason has invalid length")
        if not isinstance(command.idempotency_key, str):
            raise ValueError("idempotency key is required")
        key = command.idempotency_key.strip()
        if not 1 <= len(key) <= 128:
            raise ValueError("idempotency key has invalid length")
        return await self._repository.reopen_for_receipt(
            command.internal_order_id,
            command.expected_version,
            command.admin_telegram_user_id,
            command.actor_type,
            command.session_id,
            command.confirmation_id,
            command.request_fingerprint.lower(),
            reason,
            key,
        )
