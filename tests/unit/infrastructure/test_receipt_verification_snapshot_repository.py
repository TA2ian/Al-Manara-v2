from decimal import Decimal
from uuid import uuid4

import pytest

from app.infrastructure.persistence.receipt_verification_snapshot_repository import (
    ReceiptVerificationSnapshotPersistenceError,
    SupabaseReceiptVerificationSnapshotRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.response)


class Response:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


def snapshot_row(order_id):
    return {
        "order_id": str(order_id),
        "payment_currency": "NEW.SYP",
        "expected_payment_amount": "150000.00",
        "exchange_rate": "15000.000000000",
        "fee_percent": "5.000000",
        "rounding_policy_version": "ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001",
        "network_code": "TRC20",
        "wallet_address": "TExampleWalletAddress",
        "expected_reference": "SC-12345",
        "tolerance": "0.04",
    }


@pytest.mark.asyncio
async def test_maps_authoritative_snapshot_to_context() -> None:
    order_id = uuid4()
    client = FakeClient(Response([snapshot_row(order_id)]))

    context = await SupabaseReceiptVerificationSnapshotRepository(client).get_receipt_verification_context(order_id)

    assert context is not None
    assert context.order_id == order_id
    assert context.payment_currency.value == "NEW.SYP"
    assert context.expected_payment_amount == Decimal("150000.00")
    assert context.exchange_rate == Decimal("15000.000000000")
    assert context.fee_percent == Decimal("5.000000")
    assert context.network_code == "TRC20"
    assert context.wallet_address == "TExampleWalletAddress"
    assert context.expected_reference == "SC-12345"
    assert context.tolerance == Decimal("0.04")
    assert client.calls == [
        ("get_receipt_verification_snapshot", {"p_order_id": str(order_id)})
    ]


@pytest.mark.asyncio
async def test_missing_snapshot_returns_none() -> None:
    order_id = uuid4()
    client = FakeClient(Response([]))

    context = await SupabaseReceiptVerificationSnapshotRepository(client).get_receipt_verification_context(order_id)

    assert context is None


@pytest.mark.asyncio
async def test_rpc_error_is_not_leaked() -> None:
    order_id = uuid4()
    client = FakeClient(Response(None, error={"message": "sensitive database detail"}))

    with pytest.raises(
        ReceiptVerificationSnapshotPersistenceError,
        match="receipt verification snapshot RPC returned an error",
    ):
        await SupabaseReceiptVerificationSnapshotRepository(client).get_receipt_verification_context(order_id)


@pytest.mark.asyncio
async def test_invalid_payload_is_rejected() -> None:
    order_id = uuid4()
    row = snapshot_row(order_id)
    row["expected_payment_amount"] = "not-a-number"
    client = FakeClient(Response([row]))

    with pytest.raises(ReceiptVerificationSnapshotPersistenceError):
        await SupabaseReceiptVerificationSnapshotRepository(client).get_receipt_verification_context(order_id)


@pytest.mark.asyncio
async def test_mismatched_order_id_is_rejected() -> None:
    order_id = uuid4()
    client = FakeClient(Response([snapshot_row(uuid4())]))

    with pytest.raises(ReceiptVerificationSnapshotPersistenceError):
        await SupabaseReceiptVerificationSnapshotRepository(client).get_receipt_verification_context(order_id)
