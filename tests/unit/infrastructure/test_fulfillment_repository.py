from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.infrastructure.persistence.fulfillment_repository import (
    FulfillmentPersistenceError,
    SupabaseFulfillmentRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.responses[function_name])


class Response:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


@pytest.mark.asyncio
async def test_claim_maps_rpc_result_and_passes_session() -> None:
    order_id = uuid4()
    session_id = uuid4()
    claimed_at = datetime.now(timezone.utc)
    client = FakeClient({
        "claim_order_fulfillment": Response([{
            "internal_order_id": str(order_id),
            "public_order_code": "ORD-1",
            "status": "APPROVED",
            "version": 4,
            "admin_telegram_user_id": 123,
            "claimed_at": claimed_at.isoformat(),
            "replayed": False,
        }])
    })

    result = await SupabaseFulfillmentRepository(client).claim(order_id, 3, 123, "primary", "claim-1", session_id)

    assert result.internal_order_id == order_id
    assert result.status == "APPROVED"
    assert result.version == 4
    assert result.admin_telegram_user_id == 123
    assert result.replayed is False
    assert client.calls[0][0] == "claim_order_fulfillment"
    assert client.calls[0][1]["p_session_id"] == str(session_id)


@pytest.mark.asyncio
async def test_complete_maps_rpc_result() -> None:
    order_id = uuid4()
    session_id = uuid4()
    completed_at = datetime.now(timezone.utc)
    client = FakeClient({
        "complete_order_fulfillment": Response([{
            "internal_order_id": str(order_id),
            "public_order_code": "ORD-1",
            "status": "COMPLETED",
            "version": 5,
            "completed_at": completed_at.isoformat(),
            "replayed": True,
        }])
    })

    result = await SupabaseFulfillmentRepository(client).complete(order_id, 4, 123, "primary", "complete-1", session_id, "a"*64, uuid4(), "b"*64)

    assert result.status == "COMPLETED"
    assert result.version == 5
    assert result.admin_telegram_user_id == 123
    assert result.replayed is True
    assert client.calls[0][1]["p_session_id"] == str(session_id)


@pytest.mark.asyncio
async def test_complete_passes_transfer_reference() -> None:
    order_id = uuid4()
    session_id = uuid4()
    completed_at = datetime.now(timezone.utc)
    reference = "a" * 64
    client = FakeClient({"complete_order_fulfillment": Response([{
        "internal_order_id": str(order_id), "public_order_code": "ORD-1",
        "status": "COMPLETED", "version": 5, "completed_at": completed_at.isoformat(), "replayed": False,
    }])})
    await SupabaseFulfillmentRepository(client).complete(order_id, 4, 123, "primary", "complete-1", session_id, reference, uuid4(), "b"*64)
    assert client.calls[0][1]["p_transfer_reference"] == reference
    assert client.calls[0][1]["p_confirmation_id"]
    assert client.calls[0][1]["p_request_fingerprint"] == "b"*64


@pytest.mark.asyncio
async def test_invalid_rpc_response_is_rejected() -> None:
    order_id = uuid4()
    client = FakeClient({"claim_order_fulfillment": Response([])})

    with pytest.raises(FulfillmentPersistenceError):
        await SupabaseFulfillmentRepository(client).claim(order_id, 1, 123, "primary", "claim-1", uuid4())


@pytest.mark.asyncio
async def test_create_confirmation_uses_shared_rpc() -> None:
    confirmation_id = uuid4()
    client = FakeClient({"create_admin_action_confirmation": Response([{"confirmation_id": str(confirmation_id)}])})

    result = await SupabaseFulfillmentRepository(client).create_confirmation(
        123, "primary", uuid4(), "fulfillment.complete", "a" * 64
    )

    assert result == confirmation_id
    assert client.calls[0][0] == "create_admin_action_confirmation"
    assert client.calls[0][1]["p_operation"] == "fulfillment.complete"
