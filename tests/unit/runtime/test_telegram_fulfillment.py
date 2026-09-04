from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.fulfillment import FulfillmentResult
from app.runtime.telegram.fulfillment import TelegramFulfillmentHandler, TelegramFulfillmentInput


class FakeFulfillmentService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def claim(self, **kwargs):
        self.calls.append("claim")
        return FulfillmentResult(kwargs["internal_order_id"], "ORD-1", "APPROVED", 3, 10, datetime.now(timezone.utc), False)

    async def complete(self, **kwargs):
        self.calls.append("complete")
        return FulfillmentResult(kwargs["internal_order_id"], "ORD-1", "COMPLETED", 4, 10, datetime.now(timezone.utc), False)


@pytest.mark.asyncio
async def test_claim_accepts_valid_request() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service)  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(10, "primary", uuid4(), 2, "claim-1"))

    assert response.ok is True
    assert response.status == "APPROVED"
    assert service.calls == ["claim"]


@pytest.mark.asyncio
async def test_complete_accepts_valid_request() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service)  # type: ignore[arg-type]

    response = await handler.complete(TelegramFulfillmentInput(10, "primary", uuid4(), 3, "complete-1"))

    assert response.ok is True
    assert response.status == "COMPLETED"
    assert service.calls == ["complete"]


@pytest.mark.asyncio
async def test_invalid_request_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service)  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(0, "primary", uuid4(), 1, "claim-1"))

    assert response.ok is False
    assert service.calls == []
