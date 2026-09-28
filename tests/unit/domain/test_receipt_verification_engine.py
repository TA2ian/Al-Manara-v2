from decimal import Decimal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_engine import verify_receipt


def context(currency: str = "USD", amount: str = "100.00") -> ReceiptVerificationContext:
    return ReceiptVerificationContext(
        order_id=uuid4(),
        payment_currency=currency,
        expected_payment_amount=Decimal(amount),
        exchange_rate=None if currency == "USD" else Decimal("100.00"),
        fee_percent=Decimal("1.00"),
        rounding_policy_version="v1",
        network_code="TRC20",
        wallet_address="T9yD14Nj9j7xAB4dbGeiX9h8unkM4Jx7nQ",
        order_created_at=datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Damascus")),
        receipt_deadline_at=datetime(2026, 9, 28, 13, 0, tzinfo=ZoneInfo("Asia/Damascus")),\n        expected_reference="ORD-ABC123DEF456",
    )


def extracted(
    amount: str | None = "100.00",
    currency: str | None = "USD",
    confidence: str = "0.95",
    transaction_datetime: datetime | None = datetime(2026, 9, 28, 12, 30, tzinfo=ZoneInfo("Asia/Damascus")),
    reference: str | None = "ORD-ABC123DEF456",
) -> ExtractedReceiptData:
    return ExtractedReceiptData(
        uuid4(),
        Decimal(amount) if amount else None,
        currency,
        reference,
        "TRC20",
        Decimal(confidence),
        transaction_datetime,
    )


def test_verified_when_currency_amount_and_confidence_are_valid() -> None:
    result = verify_receipt(context(), extracted())
    assert result.decision is VerificationDecision.VERIFIED


def test_mismatch_when_currency_is_wrong() -> None:
    result = verify_receipt(context(), extracted(currency="NEW.SYP"))
    assert result.decision is VerificationDecision.MISMATCH
    assert "currency_mismatch" in result.reasons


def test_verified_when_new_syp_alias_matches_new_syp_context() -> None:
    result = verify_receipt(
        context(currency="NEW.SYP", amount="10000.00"),
        extracted(amount="10000.00", currency="NEW SYRIAN POUND"),
    )
    assert result.decision is VerificationDecision.VERIFIED


def test_verified_when_arabic_new_syp_alias_matches_new_syp_context() -> None:
    result = verify_receipt(
        context(currency="NEW.SYP", amount="10000.00"),
        extracted(amount="10000.00", currency="ليرة جديدة سورية"),
    )
    assert result.decision is VerificationDecision.VERIFIED


def test_insufficient_data_when_amount_is_missing() -> None:
    result = verify_receipt(context(), extracted(amount=None))
    assert result.decision is VerificationDecision.INSUFFICIENT_DATA


def test_suspicious_when_ocr_confidence_is_low_but_financial_match_is_exact() -> None:
    result = verify_receipt(context(), extracted(confidence="0.69"))
    assert result.decision is VerificationDecision.SUSPICIOUS


def test_mismatch_when_amount_exceeds_tolerance() -> None:
    result = verify_receipt(context(), extracted(amount="100.05"))
    assert result.decision is VerificationDecision.MISMATCH


def test_mismatch_when_transaction_time_is_before_order_creation() -> None:
    result = verify_receipt(
        context(),
        extracted(transaction_datetime=datetime(2026, 9, 28, 11, 59, tzinfo=ZoneInfo("Asia/Damascus"))),
    )
    assert result.decision is VerificationDecision.MISMATCH
    assert "transaction_time_before_order_creation" in result.reasons


def test_mismatch_when_transaction_time_is_after_receipt_deadline() -> None:
    result = verify_receipt(
        context(),
        extracted(transaction_datetime=datetime(2026, 9, 28, 13, 1, tzinfo=ZoneInfo("Asia/Damascus"))),
    )
    assert result.decision is VerificationDecision.MISMATCH
    assert "transaction_time_after_receipt_deadline" in result.reasons


def test_insufficient_data_when_transaction_time_is_missing() -> None:
    result = verify_receipt(context(), extracted(transaction_datetime=None))
    assert result.decision is VerificationDecision.INSUFFICIENT_DATA
    assert "transaction_datetime_unavailable" in result.reasons


def test_insufficient_data_when_order_reference_is_missing():
    result = verify_receipt(context(), extracted(reference=None))
    assert result.decision is VerificationDecision.INSUFFICIENT_DATA
    assert "reference_required_but_unavailable" in result.reasons


def test_mismatch_when_order_reference_is_wrong():
    result = verify_receipt(context(), extracted(reference="ORD-WRONG123456"))
    assert result.decision is VerificationDecision.MISMATCH
    assert "reference_mismatch" in result.reasons
