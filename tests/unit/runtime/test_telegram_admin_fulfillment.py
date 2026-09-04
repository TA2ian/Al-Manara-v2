from uuid import uuid4

import pytest

from app.application.fulfillment import FulfillmentResult
from app.runtime.telegram.admin_fulfillment import (
    TelegramAdminFulfillmentHandler,
    TelegramAdminFulfillmentInput,
)


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def claim(self, *args):
        self.calls.append(("claim", args))
        if self.error:
            raise self.error
        return self.result

    async def complete(self, *args):
        self.calls.append(("complete", args))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_handler_forwards_claim_request() -> None:
    order_id = uuid4()
    service = FakeService(
        FulfillmentResult(order_id, "ORD-FUL01", "APPROVED", 5, 100, __import__("datetime").datetime.now(__import__("datetime").timezone.utc), False)
    )
    handler = TelegramAdminFulfillmentHandler(service)

    response = await handler.claim(
        TelegramAdminFulfillmentInput(100, "PRIMARY", order_id, 4, "claim-1")
    )

    assert response.ok is True
    assert response.status == "APPROVED"
    assert response.version == 5
    assert service.calls[0][0] == "claim"
    assert service.calls[0][1][0] == order_id


@pytest.mark.asyncio
async def test_handler_forwards_complete_request() -> None:
    order_id = uuid4()
    service = FakeService(
        FulfillmentResult(order_id, "ORD-FUL02", "COMPLETED", 6, 100, __import__("datetime").datetime.now(__import__("datetime").timezone.utc), False)
    )
    handler = TelegramAdminFulfillmentHandler(service)

    response = await handler.complete(
        TelegramAdminFulfillmentInput(100, "backup", order_id, 5, "complete-1")
    )

    assert response.ok is True
    assert response.status == "COMPLETED"
    assert service.calls[0][0] == "complete"


@pytest.mark.asyncio
async def test_handler_rejects_invalid_request_without_calling_service() -> None:
    service = FakeService()
    handler = TelegramAdminFulfillmentHandler(service)

    response = await handler.claim(
        TelegramAdminFulfillmentInput(0, "primary", uuid4(), 1, "key")
    )

    assert response.ok is False
    assert response.message == "invalid fulfillment request"
    assert service.calls == []


@pytest.mark.asyncio
async def test_handler_hides_persistence_errors() -> None:
    service = FakeService(error=RuntimeError("stale order version"))
    handler = TelegramAdminFulfillmentHandler(service)

    response = await handler.complete(
        TelegramAdminFulfillmentInput(100, "primary", uuid4(), 3, "key")
    )

    assert response.ok is False
    assert "stale" not in response.message
