from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.fulfillment import FulfillmentResult, FulfillmentService


class FakeFulfillmentRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def claim(self, *args):
        self.calls.append(("claim", args))
        return FulfillmentResult(uuid4(), "ORD-1", "APPROVED", 3, 100, datetime.now(timezone.utc), False)

    async def complete(self, *args):
        self.calls.append(("complete", args))
        return FulfillmentResult(uuid4(), "ORD-1", "COMPLETED", 4, 100, datetime.now(timezone.utc), False)


@pytest.mark.asyncio
async def test_claim_normalizes_actor_and_idempotency_key() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    result = await service.claim(uuid4(), 2, 100, " PRIMARY ", "  claim-1  ")

    assert result.status == "APPROVED"
    assert repository.calls[0][0] == "claim"
    assert repository.calls[0][1][3:] == ("primary", "claim-1")


@pytest.mark.asyncio
async def test_complete_delegates_to_atomic_repository() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    result = await service.complete(uuid4(), 3, 100, "backup", "complete-1")

    assert result.status == "COMPLETED"
    assert repository.calls[0][0] == "complete"


@pytest.mark.asyncio
async def test_invalid_request_is_rejected_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="expected version"):
        await service.claim(uuid4(), 0, 100, "primary", "claim-1")
    assert repository.calls == []
