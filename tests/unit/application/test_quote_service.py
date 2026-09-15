from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.quote import ExchangeRateSnapshot, FeePolicySnapshot
from app.application.quote_service import QuoteRequest, QuoteService


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeRates:
    async def get_current_rate(self, currency: str, now: datetime):
        return ExchangeRateSnapshot(currency, Decimal("135"), now, "settings", "rate-v1")


class FakeFees:
    async def get_current_policy(self, network_code: str, now: datetime):
        return FeePolicySnapshot(Decimal("10"), "fee-v1", now)


@pytest.mark.asyncio
async def test_quote_captures_rate_fee_and_expiry() -> None:
    issued = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    service = QuoteService(
        FakeRates(),
        FakeFees(),
        FixedClock(issued),
        timedelta(minutes=10),
        "ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001",
    )

    quote = await service.create_quote(QuoteRequest("BEP20", Decimal("100"), "NEW.SYP"))

    assert quote.financials.local_amount == Decimal("13500.00")
    assert quote.financials.net_usdt_amount == Decimal("90.000")
    assert quote.exchange_rate_snapshot is not None
    assert quote.exchange_rate_snapshot.rate == Decimal("135")
    assert quote.fee_policy_snapshot.percent == Decimal("10")
    assert quote.expires_at == issued + timedelta(minutes=10)


@pytest.mark.asyncio
async def test_quote_accepts_new_syp_alias_and_network_alias() -> None:
    issued = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    service = QuoteService(
        FakeRates(),
        FakeFees(),
        FixedClock(issued),
        timedelta(minutes=10),
        "v1",
    )

    quote = await service.create_quote(
        QuoteRequest("TRC-20", Decimal("100"), "ليرة سورية جديدة")
    )

    assert quote.financials.payment_currency == "NEW.SYP"
    assert quote.financials.local_amount == Decimal("13500.00")


@pytest.mark.asyncio
async def test_quote_rejects_unknown_currency() -> None:
    issued = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    service = QuoteService(FakeRates(), FakeFees(), FixedClock(issued), timedelta(minutes=10), "v1")

    with pytest.raises(ValueError, match="unsupported payment currency"):
        await service.create_quote(QuoteRequest("BEP20", Decimal("100"), "EUR"))


def test_quote_expiry_is_deterministic() -> None:
    issued = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    service = QuoteService(FakeRates(), FakeFees(), FixedClock(issued), timedelta(minutes=10), "v1")

    class Quote:
        pass

    quote = Quote()
    quote.expires_at = issued + timedelta(minutes=10)

    assert service.is_expired(quote, issued + timedelta(minutes=9)) is False
    assert service.is_expired(quote, issued + timedelta(minutes=10)) is True
