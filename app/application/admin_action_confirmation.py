from __future__ import annotations

from typing import Protocol
from uuid import UUID


class AdminActionConfirmationRepository(Protocol):
    async def create(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
        operation: str,
        request_fingerprint: str,
    ) -> UUID: ...


class AdminActionConfirmationService:
    ALLOWED_OPERATIONS = frozenset({"order.reopen_receipt", "fulfillment.complete", "admin_payment_account.upsert", "admin_payment_account.status"})

    def __init__(self, repository: AdminActionConfirmationRepository) -> None:
        self._repository = repository

    async def create(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
        operation: str,
        request_fingerprint: str,
    ) -> UUID:
        if not isinstance(admin_telegram_user_id, int) or admin_telegram_user_id <= 0:
            raise ValueError("administrator identity is required")
        if actor_type not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if not isinstance(session_id, UUID):
            raise ValueError("administrator session is required")
        if operation not in self.ALLOWED_OPERATIONS:
            raise ValueError("unsupported confirmation operation")
        if not isinstance(request_fingerprint, str) or len(request_fingerprint) != 64 or any(c not in "0123456789abcdef" for c in request_fingerprint):
            raise ValueError("invalid request fingerprint")
        return await self._repository.create(admin_telegram_user_id, actor_type, session_id, operation, request_fingerprint)
