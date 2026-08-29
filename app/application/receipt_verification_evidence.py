from __future__ import annotations

from app.domain.network import normalize_network
from app.domain.receipt_evidence import EvidenceMatch, VerificationEvidence
from app.domain.receipt_reference import operation_numbers_match
from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_engine import VerificationEngineResult


def build_verification_evidence(
    context: ReceiptVerificationContext,
    extracted: ExtractedReceiptData,
    result: VerificationEngineResult,
) -> VerificationEvidence:
    if extracted.amount is None:
        amount = EvidenceMatch.UNAVAILABLE
    elif result.financial_match is not None and result.financial_match.decision is VerificationDecision.VERIFIED:
        amount = EvidenceMatch.MATCHED
    else:
        amount = EvidenceMatch.MISMATCHED

    if extracted.currency is None:
        currency = EvidenceMatch.UNAVAILABLE
    elif extracted.currency == context.payment_currency.value:
        currency = EvidenceMatch.MATCHED
    else:
        currency = EvidenceMatch.MISMATCHED

    if extracted.network is None:
        network = EvidenceMatch.UNAVAILABLE
    else:
        normalized = normalize_network(extracted.network)
        network = EvidenceMatch.MATCHED if normalized is not None and normalized.value == context.network_code else EvidenceMatch.MISMATCHED

    operation_number = EvidenceMatch.UNAVAILABLE
    if context.expected_operation_number is not None:
        operation_match = operation_numbers_match(context.expected_operation_number, extracted.operation_number)
        operation_number = EvidenceMatch.MATCHED if operation_match is True else EvidenceMatch.MISMATCHED if operation_match is False else EvidenceMatch.UNAVAILABLE
    elif extracted.operation_number:
        operation_number = EvidenceMatch.NOT_CHECKED

    return VerificationEvidence(
        amount=amount,
        currency=currency,
        network=network,
        reference=operation_number,
        ocr_confidence=extracted.confidence,
        tolerance_used=context.tolerance,
        reasons=result.reasons,
        decision=result.decision,
    )
