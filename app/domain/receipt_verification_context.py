from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.receipt_verification import ABSOLUTE_TOLERANCE


@dataclass(frozen=True, slots=True)
class ReceiptVerificationContext:
    order_id: UUID
    payment_currency: str
    expected_payment_amount: Decimal
    exchange_rate: Decimal | None
    fee_percent: Decimal
    rounding_policy_version: str
    tolerance: Decimal = ABSOLUTE_TOLERANCE

    def __post_init__(self) -> None:
        if self.expected_payment_amount <= 0:
            raise ValueError("expected payment amount must be positive")
        if self.payment_currency not in {"USD", "NEW.SYP"}:
            raise ValueError("unsupported payment currency")
        if self.payment_currency == "NEW.SYP" and (self.exchange_rate is None or self.exchange_rate <= 0):
            raise ValueError("NEW.SYP verification requires exchange rate snapshot")
        if self.payment_currency == "USD" and self.exchange_rate is not None:
            raise ValueError("USD verification must not carry an exchange rate")
        if self.fee_percent < 0 or self.fee_percent >= 100:
            raise ValueError("invalid fee percent")
        if not self.rounding_policy_version.strip():
            raise ValueError("rounding policy version is required")
        if self.tolerance < 0:
            raise ValueError("tolerance cannot be negative")
