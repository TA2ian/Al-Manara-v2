from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.fulfillment import FulfillmentResult
from app.runtime.telegram.fulfillment import TelegramFulfillmentHandler, TelegramFulfillmentInput


class FakeFulfillmentService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.claim_kwargs = None
        self.complete_kwargs = None

    async def claim(self, **kwargs):
        self.calls.append("claim")
        self.claim_kwargs = kwargs
        return FulfillmentResult(kwargs["internal_order_id"], "ORD-1", "APPROVED", 3, 10, datetime.now(timezone.utc), False)

    async def complete(self, **kwargs):
        self.calls.append("complete")
        self.complete_kwargs = kwargs
        return FulfillmentResult(kwargs["internal_order_id"], "ORD-1", "COMPLETED", 4, 10, datetime.now(timezone.utc), False)


class FakeSessionValidator:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.calls = []

    async def validate_session(self, telegram_user_id: int, actor_type: str, session_id):
        self.calls.append((telegram_user_id, actor_type, session_id))
        return self.valid


@pytest.mark.asyncio
async def test_claim_accepts_valid_request() -> None:
    service = FakeFulfillmentService()
    session_validator = FakeSessionValidator()
    handler = TelegramFulfillmentHandler(service, session_validator=session_validator)  # type: ignore[arg-type]
    session_id = uuid4()

    response = await handler.claim(TelegramFulfillmentInput(10, "primary", uuid4(), 2, "claim-1", session_id))

    assert response.ok is True
    assert response.status == "APPROVED"
    assert service.calls == ["claim"]
    assert session_validator.calls[0] == (10, "primary", session_id)


@pytest.mark.asyncio
async def test_complete_accepts_valid_request() -> None:
    service = FakeFulfillmentService()
    session_validator = FakeSessionValidator()
    handler = TelegramFulfillmentHandler(service, session_validator=session_validator)  # type: ignore[arg-type]

    response = await handler.complete(TelegramFulfillmentInput(10, "primary", uuid4(), 3, "complete-1", uuid4(), "a"*64))

    assert response.ok is True
    assert response.status == "COMPLETED"
    assert service.calls == ["complete"]
    assert service.complete_kwargs["manual_usdt_transfer_reference"] == "a" * 64
    assert service.complete_kwargs["idempotency_key"] == "complete-1"


@pytest.mark.asyncio
async def test_missing_session_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service, session_validator=FakeSessionValidator())  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(10, "primary", uuid4(), 1, "claim-1", None))

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_expired_or_revoked_session_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service, session_validator=FakeSessionValidator(False))  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(10, "primary", uuid4(), 1, "claim-1", uuid4()))

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_invalid_request_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service, session_validator=FakeSessionValidator())  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(0, "primary", uuid4(), 1, "claim-1", uuid4()))

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_invalid_order_identity_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service, session_validator=FakeSessionValidator())  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(10, "primary", "not-a-uuid", 1, "claim-1", uuid4()))  # type: ignore[arg-type]

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_invalid_actor_type_never_calls_application() -> None:
    service = FakeFulfillmentService()
    handler = TelegramFulfillmentHandler(service, session_validator=FakeSessionValidator())  # type: ignore[arg-type]

    response = await handler.claim(TelegramFulfillmentInput(10, None, uuid4(), 1, "claim-1", uuid4()))  # type: ignore[arg-type]

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_complete_requires_transfer_reference() -> None:
    service = FakeFulfillmentService()
    session_validator = FakeSessionValidator()
    handler = TelegramFulfillmentHandler(service, session_validator=session_validator)  # type: ignore[arg-type]

    response = await handler.complete(TelegramFulfillmentInput(10, "primary", uuid4(), 3, "complete-1", uuid4()))

    assert response.ok is False
    assert service.calls == []
