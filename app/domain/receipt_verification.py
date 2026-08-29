from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


ABSOLUTE_TOLERANCE = Decimal("0.04")


class VerificationDecision(StrEnum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    INSUFFICIENT_DATA = "insufficient_data"
    UNREADABLE = "unreadable"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True, slots=True)
class ExtractedReceiptData:
    receipt_id: UUID
    amount: Decimal | None
    currency: str | None
    reference: str | None
    network: str | None
    confidence: Decimal

    def __post_init__(self) -> None:
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("receipt confidence must be between 0 and 1")
        if self.amount is not None and (not self.amount.is_finite() or self.amount <= 0):
            raise ValueError("receipt amount must be positive and finite")


@dataclass(frozen=True, slots=True)
class FinancialMatchResult:
    decision: VerificationDecision
    expected_amount: Decimal
    extracted_amount: Decimal | None
    absolute_difference: Decimal | None


def match_receipt_amount(expected_amount: Decimal, extracted: ExtractedReceiptData) -> FinancialMatchResult:
    if extracted.amount is None or extracted.currency is None:
        return FinancialMatchResult(VerificationDecision.INSUFFICIENT_DATA, expected_amount, extracted.amount, None)

    if extracted.currency != "USD":
        return FinancialMatchResult(VerificationDecision.MISMATCH, expected_amount, extracted.amount, abs(expected_amount - extracted.amount))

    difference = abs(expected_amount - extracted.amount)
    decision = VerificationDecision.VERIFIED if difference <= ABSOLUTE_TOLERANCE else VerificationDecision.MISMATCH
    return FinancialMatchResult(decision, expected_amount, extracted.amount, difference)
