from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.currency import CurrencyCode
from app.domain.receipt_ocr import OcrFieldValue
from app.domain.receipt_verification import ExtractedReceiptData, FinancialMatchResult, VerificationDecision
from app.domain.receipt_verification_context import ReceiptVerificationContext


@dataclass(frozen=True, slots=True)
class VerificationEngineResult:
    decision: VerificationDecision
    financial_match: FinancialMatchResult | None
    reasons: tuple[str, ...]


def _field(fields: dict, key):
    value = fields.get(key)
    return value.value.strip() if isinstance(value, OcrFieldValue) else None


def verify_receipt(context: ReceiptVerificationContext, extracted: ExtractedReceiptData) -> VerificationEngineResult:
    reasons: list[str] = []

    if extracted.confidence < Decimal("0.70"):
        reasons.append("ocr_confidence_below_threshold")

    if extracted.currency is None or extracted.amount is None:
        return VerificationEngineResult(VerificationDecision.INSUFFICIENT_DATA, None, tuple(reasons + ["missing_amount_or_currency"]))

    if extracted.currency != context.payment_currency:
        return VerificationEngineResult(VerificationDecision.MISMATCH, None, tuple(reasons + ["currency_mismatch"]))

    financial = FinancialMatchResult(
        decision=VerificationDecision.VERIFIED,
        expected_amount=context.expected_payment_amount,
        extracted_amount=extracted.amount,
        absolute_difference=abs(context.expected_payment_amount - extracted.amount),
    )
    if financial.absolute_difference is None or financial.absolute_difference > context.tolerance:
        return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["amount_mismatch"]))

    if extracted.network is not None and extracted.network.strip().upper() != context.payment_currency.strip().upper() and context.payment_currency != CurrencyCode.USD:
        reasons.append("network_requires_contextual_validation")

    if extracted.confidence < Decimal("0.70"):
        return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons))

    return VerificationEngineResult(VerificationDecision.VERIFIED, financial, tuple(reasons))
