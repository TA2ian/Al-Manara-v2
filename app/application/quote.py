from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from app.domain.money import OrderFinancials


@dataclass(frozen=True, slots=True)
class ExchangeRateSnapshot:
    currency: str
    rate: Decimal
    captured_at: datetime
    source: str
    version: str

    def __post_init__(self) -> None:
        if not self.rate.is_finite() or self.rate <= 0:
            raise ValueError("exchange rate must be positive and finite")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if not self.source.strip():
            raise ValueError("exchange rate source is required")
        if not self.version.strip():
            raise ValueError("exchange rate version is required")


@dataclass(frozen=True, slots=True)
class FeePolicySnapshot:
    percent: Decimal
    version: str
    effective_at: datetime

    def __post_init__(self) -> None:
        if self.percent < 0 or self.percent >= 100:
            raise ValueError("fee percent must be in [0, 100)")
        if self.effective_at.tzinfo is None:
            raise ValueError("effective_at must be timezone-aware")
        if not self.version.strip():
            raise ValueError("fee policy version is required")


@dataclass(frozen=True, slots=True)
class PurchaseQuote:
    financials: OrderFinancials
    exchange_rate_snapshot: ExchangeRateSnapshot | None
    fee_policy_snapshot: FeePolicySnapshot
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("quote expiry must be timezone-aware")
        if self.exchange_rate_snapshot is None and self.financials.payment_currency != "USD":
            raise ValueError("non-USD quote requires exchange rate snapshot")
