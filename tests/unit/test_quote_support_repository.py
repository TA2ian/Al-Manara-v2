from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from app.infrastructure.persistence.quote_support_repository import (
    QuoteSupportPersistenceError,
    SupabaseExchangeRateProvider,
    SupabaseFeePolicyProvider,
    UtcQuoteClock,
    UuidPublicOrderCodeGenerator,
)


class Response:
    def __init__(self, data: Any, error: Any = None) -> None:
        self.data = data
        self.error = error


class Query:
    def __init__(self, response: Response) -> None:
        self.response = response

    def execute(self) -> Response:
        return self.response


class Client:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, function_name: str, params: dict[str, Any]) -> Query:
        self.calls.append((function_name, params))
        return Query(self.response)


@pytest.mark.asyncio
async def test_fee_policy_provider_maps_authoritative_snapshot() -> None:
    client = Client(Response([{"percent": "10.000000", "version": "network_config:3", "effective_at": "2026-09-04T10:00:00+00:00"}]))
    now = datetime(2026, 9, 4, 11, tzinfo=timezone.utc)

    result = await SupabaseFeePolicyProvider(client).get_current_policy("bep20", now)

    assert result is not None
    assert result.percent == Decimal("10.000000")
    assert result.version == "network_config:3"
    assert result.effective_at.tzinfo is not None
    assert client.calls[0][0] == "get_current_fee_policy"
    assert client.calls[0][1]["p_network_code"] == "BEP20"


@pytest.mark.asyncio
async def test_exchange_rate_provider_maps_snapshot() -> None:
    client = Client(Response([{"currency": "NEW.SYP", "rate": "15000.125", "captured_at": "2026-09-04T10:30:00+00:00", "source": "settings.active_exchange_rate_id", "version": "exchange_rate:abc"}]))
    now = datetime(2026, 9, 4, 11, tzinfo=timezone.utc)

    result = await SupabaseExchangeRateProvider(client).get_current_rate("new.syp", now)

    assert result is not None
    assert result.currency == "NEW.SYP"
    assert result.rate == Decimal("15000.125")
    assert result.version == "exchange_rate:abc"
    assert client.calls[0][0] == "get_current_exchange_rate"


@pytest.mark.asyncio
async def test_provider_returns_none_when_no_current_snapshot_exists() -> None:
    client = Client(Response([]))
    now = datetime.now(timezone.utc)

    assert await SupabaseFeePolicyProvider(client).get_current_policy("BEP20", now) is None
    assert await SupabaseExchangeRateProvider(client).get_current_rate("NEW.SYP", now) is None


@pytest.mark.asyncio
async def test_provider_rejects_invalid_payload() -> None:
    client = Client(Response([{"percent": "not-a-number", "version": "x", "effective_at": "2026-09-04T10:00:00+00:00"}]))

    with pytest.raises(QuoteSupportPersistenceError):
        await SupabaseFeePolicyProvider(client).get_current_policy("BEP20", datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_provider_wraps_rpc_failure() -> None:
    client = Client(Response(None, error={"message": "database unavailable"}))

    with pytest.raises(QuoteSupportPersistenceError, match="database unavailable"):
        await SupabaseFeePolicyProvider(client).get_current_policy("BEP20", datetime.now(timezone.utc))


def test_utc_clock_is_timezone_aware() -> None:
    assert UtcQuoteClock().now().tzinfo is not None


def test_public_order_code_generator_has_expected_shape() -> None:
    generator = UuidPublicOrderCodeGenerator("ord")
    value = generator.generate()
    assert value.startswith("ORD-")
    assert len(value) == 16


def test_public_order_code_generator_rejects_invalid_prefix() -> None:
    with pytest.raises(ValueError):
        UuidPublicOrderCodeGenerator("   ")
