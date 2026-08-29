from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.network import normalize_network
from app.domain.receipt_reference import references_match
from app.domain.receipt_verification import ExtractedReceiptData, FinancialMatchResult, VerificationDecision, match_receipt_amount
from app.domain.receipt_verification_context import ReceiptVerificationContext


@dataclass(frozen=True, slots=True)
class VerificationEngineResult:
    decision: VerificationDecision
    financial_match: FinancialMatchResult | None
    reasons: tuple[str, ...]


def verify_receipt(context: ReceiptVerificationContext, extracted: ExtractedReceiptData) -> VerificationEngineResult:
    reasons: list[str] = []

    if extracted.confidence < Decimal("0.70"):
        reasons.append("ocr_confidence_below_threshold")

    if extracted.currency is None or extracted.amount is None:
        return VerificationEngineResult(VerificationDecision.INSUFFICIENT_DATA, None, tuple(reasons + ["missing_amount_or_currency"]))

    if extracted.currency != context.payment_currency.value:
        return VerificationEngineResult(VerificationDecision.MISMATCH, None, tuple(reasons + ["currency_mismatch"]))

    financial = match_receipt_amount(context.expected_payment_amount, extracted, context.tolerance)
    if financial.decision is VerificationDecision.MISMATCH:
        return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["amount_mismatch"]))

    if extracted.network is not None:
        normalized_network = normalize_network(extracted.network)
        if normalized_network is None:
            return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons + ["unknown_network"]))
        if normalized_network.value != context.network_code:
            return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["network_mismatch"]))

    reference_result = references_match(context.wallet_address, extracted.reference)
    if reference_result is False:
        return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["reference_mismatch"]))
    if reference_result is None:
        reasons.append("reference_not_available")

    if extracted.confidence < Decimal("0.70"):
        return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons))

    return VerificationEngineResult(VerificationDecision.VERIFIED, financial, tuple(reasons))
