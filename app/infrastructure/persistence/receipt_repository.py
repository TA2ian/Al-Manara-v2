from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.application.receipt_ports import ReceiptAttemptRepository
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, ReceiptInputType


class SupabaseReceiptAttemptRepository(ReceiptAttemptRepository):
    """Supabase adapter for receipt attempt reservation/finalization."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def reserve_next_attempt(self, *, order_id: UUID, telegram_user_id: int, idempotency_key: str, submitted_at: datetime, input_type: ReceiptInputType, transaction_reference: str | None, mime_type: str | None, telegram_file_id: str | None):
        raise NotImplementedError

    async def finalize(self, attempt_id: UUID, status: ReceiptAttemptStatus, reason: str | None = None):
        raise NotImplementedError

    async def escalate(self, order_id: UUID, attempt_id: UUID, reason: str):
        raise NotImplementedError
