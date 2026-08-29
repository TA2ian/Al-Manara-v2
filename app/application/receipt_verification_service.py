from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.receipt_verification import ExtractedReceiptData, FinancialMatchResult, match_receipt_amount
from app.domain.receipt_verification_context import ReceiptVerificationContext


@dataclass(frozen=True, slots=True)
class ReceiptVerificationInput:
    order_id: UUID
    extracted: ExtractedReceiptData


class OrderVerificationSnapshotReader(Protocol):
    async def get_receipt_verification_context(self, order_id: UUID) -> ReceiptVerificationContext | None: ...


class ReceiptFinancialVerificationService:
    def __init__(self, snapshots: OrderVerificationSnapshotReader) -> None:
        self._snapshots = snapshots

    async def verify(self, request: ReceiptVerificationInput) -> FinancialMatchResult:
        context = await self._snapshots.get_receipt_verification_context(request.order_id)
        if context is None:
            raise LookupError("order verification snapshot not found")

        extracted = request.extracted
        if extracted.currency is not None and extracted.currency != context.payment_currency:
            return FinancialMatchResult(
                decision="mismatch",
                expected_amount=context.expected_payment_amount,
                extracted_amount=extracted.amount,
                absolute_difference=(abs(context.expected_payment_amount - extracted.amount) if extracted.amount is not None else None),
            )

        return match_receipt_amount(context.expected_payment_amount, extracted)
