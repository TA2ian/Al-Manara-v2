from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.receipt_evidence import VerificationEvidence
from app.domain.receipt_verification import ExtractedReceiptData
from app.application.receipt_verification_service import ReceiptFinancialVerificationService, ReceiptVerificationInput


@dataclass(frozen=True, slots=True)
class AdminReceiptRecheckCommand:
    order_id: UUID
    admin_telegram_user_id: int
    actor_type: str
    session_id: UUID
    extracted: ExtractedReceiptData


class AdminReceiptRecheckAuthorization(Protocol):
    async def authorize(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> bool: ...


class AdminReceiptRecheckService:
    """Read-only administrative financial recheck.

    It produces evidence from the immutable order verification snapshot and never
    approves, rejects, or mutates the order.
    """

    def __init__(
        self,
        authorization: AdminReceiptRecheckAuthorization,
        verification: ReceiptFinancialVerificationService,
    ) -> None:
        self._authorization = authorization
        self._verification = verification

    async def recheck(self, command: AdminReceiptRecheckCommand) -> VerificationEvidence:
        if not isinstance(command.order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.admin_telegram_user_id, int) or command.admin_telegram_user_id <= 0:
            raise ValueError("admin identity is required")
        if command.actor_type not in {"primary", "backup"}:
            raise ValueError("invalid admin actor type")
        if not isinstance(command.session_id, UUID):
            raise ValueError("recent admin session is required")
        if not await self._authorization.authorize(
            command.admin_telegram_user_id, command.actor_type, command.session_id
        ):
            raise PermissionError("admin is not authorized for receipt recheck")
        return (await self._verification.verify(
            ReceiptVerificationInput(command.order_id, command.extracted)
        )).evidence
