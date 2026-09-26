from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.fulfillment import FulfillmentResult, FulfillmentService


class FakeFulfillmentRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def create_confirmation(self, *args):
        self.calls.append(("create_confirmation", args))
        return uuid4()

    async def claim(self, *args):
        self.calls.append(("claim", args))
        return FulfillmentResult(uuid4(), "ORD-1", "APPROVED", 3, 100, datetime.now(timezone.utc), False)

    async def complete(self, *args):
        self.calls.append(("complete", args))
        return FulfillmentResult(uuid4(), "ORD-1", "COMPLETED", 4, 100, datetime.now(timezone.utc), False)


@pytest.mark.asyncio
async def test_claim_normalizes_actor_and_idempotency_key_and_passes_session() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)
    session_id = uuid4()

    result = await service.claim(uuid4(), 2, 100, " PRIMARY ", "  claim-1  ", session_id)

    assert result.status == "APPROVED"
    assert repository.calls[0][0] == "claim"
    assert repository.calls[0][1][3:] == ("primary", "claim-1", session_id)


@pytest.mark.asyncio
async def test_complete_delegates_to_atomic_repository_with_session() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)
    session_id = uuid4()

    confirmation_id = uuid4()
    result = await service.complete(uuid4(), 3, 100, "backup", "complete-1", session_id, "a"*64, confirmation_id)

    assert result.status == "COMPLETED"
    assert repository.calls[0][0] == "complete"
    assert repository.calls[0][1][6] == "a"*64
    assert repository.calls[0][1][7] == confirmation_id
    assert len(repository.calls[0][1][8]) == 64


@pytest.mark.asyncio
async def test_missing_session_is_rejected_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="recent admin session"):
        await service.claim(uuid4(), 2, 100, "primary", "claim-1", None)
    assert repository.calls == []


@pytest.mark.asyncio
async def test_invalid_request_is_rejected_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="expected version"):
        await service.claim(uuid4(), 0, 100, "primary", "claim-1", uuid4())
    assert repository.calls == []


@pytest.mark.asyncio
async def test_invalid_order_identity_is_rejected_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="order id"):
        await service.claim("not-a-uuid", 1, 100, "primary", "claim-1", uuid4())
    assert repository.calls == []


@pytest.mark.asyncio
async def test_complete_rejects_missing_transfer_reference_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)
    with pytest.raises(ValueError, match="manual USDT transfer reference"):
        await service.complete(uuid4(), 3, 100, "primary", "complete-1", uuid4(), "", uuid4())
    assert repository.calls == []


@pytest.mark.asyncio
async def test_complete_rejects_invalid_transfer_reference_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="transfer reference"):
        await service.complete(uuid4(), 3, 100, "primary", "complete-1", uuid4(), "not-a-txid", uuid4())
    assert repository.calls == []


@pytest.mark.asyncio
async def test_complete_confirmation_is_created_from_bound_request() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)
    order_id = uuid4()
    session_id = uuid4()

    confirmation_id = await service.request_complete_confirmation(
        order_id, 3, 100, "primary", "complete-1", session_id, "a" * 64
    )

    assert confirmation_id
    assert repository.calls[0][0] == "create_confirmation"
    args = repository.calls[0][1]
    assert args[0:3] == (100, "primary", session_id)
    assert args[3] == "fulfillment.complete"
    assert len(args[4]) == 64


@pytest.mark.asyncio
async def test_complete_requires_confirmation_before_persistence() -> None:
    repository = FakeFulfillmentRepository()
    service = FulfillmentService(repository)

    with pytest.raises(ValueError, match="fulfillment confirmation"):
        await service.complete(uuid4(), 3, 100, "primary", "complete-1", uuid4(), "a" * 64, None)

    assert repository.calls == []
