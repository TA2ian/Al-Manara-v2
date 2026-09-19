from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.domain.order_status import OrderStatus
from app.runtime.telegram.admin_order_review import (
    TelegramAdminOrderReviewHandler,
    TelegramAdminReviewInput,
)


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.commands = []

    async def review(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result


class FakeSessionValidator:
    def __init__(self, valid=True):
        self.valid = valid
        self.calls = []

    async def validate_session(self, telegram_user_id, actor_type, session_id):
        self.calls.append((telegram_user_id, actor_type, session_id))
        return self.valid


class FakeActorResolver:
    async def resolve_actor_type(self, telegram_user_id):
        return "primary"


@pytest.mark.asyncio
async def test_admin_review_approve_returns_state_with_recent_session():
    service = FakeService(SimpleNamespace(state_after=OrderStatus.APPROVED))
    validator = FakeSessionValidator()
    session_id = uuid4()
    handler = TelegramAdminOrderReviewHandler(service, FakeActorResolver(), validator)

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=123,
            actor_type="backup",
            order_id=uuid4(),
            expected_version=4,
            action="approve",
            idempotency_key="review-1",
            session_id=session_id,
        )
    )

    assert response.ok is True
    assert response.state_after == "APPROVED"
    assert service.commands[0].actor_telegram_user_id == 123
    assert service.commands[0].expected_version == 4
    assert validator.calls == [(123, "primary", session_id)]


@pytest.mark.asyncio
async def test_admin_review_rejects_missing_session_before_service():
    service = FakeService(SimpleNamespace(state_after=OrderStatus.APPROVED))
    handler = TelegramAdminOrderReviewHandler(service, FakeActorResolver(), FakeSessionValidator())

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=123,
            actor_type="primary",
            order_id=uuid4(),
            expected_version=1,
            action="approve",
            idempotency_key="review-2",
        )
    )

    assert response.ok is False
    assert response.message == "A recent admin session is required."
    assert service.commands == []


@pytest.mark.asyncio
async def test_admin_review_rejects_invalid_identity_before_service():
    service = FakeService(SimpleNamespace(state_after=OrderStatus.REJECTED))
    handler = TelegramAdminOrderReviewHandler(service, FakeActorResolver(), FakeSessionValidator())

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=0,
            actor_type="primary",
            order_id=uuid4(),
            expected_version=1,
            action="reject",
            reason="invalid payment",
            idempotency_key="review-3",
            session_id=uuid4(),
        )
    )

    assert response.ok is False
    assert service.commands == []


@pytest.mark.asyncio
async def test_admin_review_maps_unauthorized_without_leaking_details():
    service = FakeService(error=PermissionError("internal authorization detail"))
    handler = TelegramAdminOrderReviewHandler(service, FakeActorResolver(), FakeSessionValidator())

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=123,
            actor_type="backup",
            order_id=UUID("00000000-0000-0000-0000-000000000001"),
            expected_version=1,
            action="approve",
            idempotency_key="review-4",
            session_id=uuid4(),
        )
    )

    assert response.ok is False
    assert response.message == "You are not authorized to review orders."
    assert "internal authorization detail" not in response.message


@pytest.mark.asyncio
async def test_admin_review_maps_conflict_to_retryable_message():
    service = FakeService(error=RuntimeError("stale version"))
    handler = TelegramAdminOrderReviewHandler(service, FakeActorResolver(), FakeSessionValidator())

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=123,
            actor_type="primary",
            order_id=uuid4(),
            expected_version=2,
            action="approve",
            idempotency_key="review-5",
            session_id=uuid4(),
        )
    )

    assert response.ok is False
    assert response.message == "The order could not be updated. Please retry."


@pytest.mark.asyncio
async def test_admin_review_rejects_expired_or_revoked_session_before_service():
    service = FakeService(SimpleNamespace(state_after=OrderStatus.APPROVED))
    handler = TelegramAdminOrderReviewHandler(
        service, FakeActorResolver(), FakeSessionValidator(valid=False)
    )

    response = await handler.handle(
        TelegramAdminReviewInput(
            admin_user_id=123,
            actor_type="primary",
            order_id=uuid4(),
            expected_version=2,
            action="approve",
            idempotency_key="review-6",
            session_id=uuid4(),
        )
    )

    assert response.ok is False
    assert response.message == "The admin session is no longer valid. Please retry."
    assert service.commands == []
