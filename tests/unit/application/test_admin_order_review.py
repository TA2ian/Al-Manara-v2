from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.admin_order_review import AdminOrderReviewService, AdminReviewOrderCommand
from app.application.ports import PersistedOrderTransition
from app.domain.order import Order
from app.domain.order_status import OrderStatus


class FakeTransitions:
    def __init__(self, order: Order):
        self.order = order
        self.commands = []

    async def transition(
        self,
        internal_order_id,
        target_status,
        expected_version,
        actor_telegram_user_id,
        actor_type,
        idempotency_key,
        event_payload,
        session_id,
        confirmation_id,
        request_fingerprint,
    ):
        self.commands.append({
            "internal_order_id": internal_order_id,
            "target_status": target_status,
            "expected_version": expected_version,
            "actor_telegram_user_id": actor_telegram_user_id,
            "actor_type": actor_type,
            "idempotency_key": idempotency_key,
            "event_payload": event_payload,
            "session_id": session_id,
            "confirmation_id": confirmation_id,
            "request_fingerprint": request_fingerprint,
        })
        state_before = self.order.status
        updated = self.order.transition_to(target_status)
        result = PersistedOrderTransition(
            order=updated,
            state_before=state_before,
            state_after=updated.status,
            transitioned_at=datetime.now(timezone.utc),
        )
        self.order = updated
        return result


class FakeAdminAuthorization:
    def __init__(self, authorized: bool = True):
        self.authorized = authorized
        self.calls = []

    async def authorize(self, telegram_user_id: int, actor_type: str) -> bool:
        self.calls.append((telegram_user_id, actor_type))
        return self.authorized


@pytest.mark.asyncio
async def test_admin_approval_uses_confirmation_and_binds_session() -> None:
    order = Order(uuid4(), "ORD-REVIEW01", OrderStatus.UNDER_REVIEW, 2)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization()
    service = AdminOrderReviewService(transitions, authorization)
    session_id = uuid4()
    confirmation_id = uuid4()
    fingerprint = AdminOrderReviewService.review_fingerprint(
        order.internal_order_id, 2, 1001, "primary", "approve", None, "review-approve-1"
    )

    result = await service.review(AdminReviewOrderCommand(
        internal_order_id=order.internal_order_id,
        actor_telegram_user_id=1001,
        actor_type="primary",
        expected_version=2,
        action="approve",
        idempotency_key="review-approve-1",
        session_id=session_id,
        confirmation_id=confirmation_id,
        request_fingerprint=fingerprint,
    ))

    assert result.state_after is OrderStatus.APPROVED
    assert transitions.commands[0]["event_payload"] is None
    assert transitions.commands[0]["session_id"] == session_id
    assert transitions.commands[0]["confirmation_id"] == confirmation_id
    assert transitions.commands[0]["target_status"] is OrderStatus.APPROVED
    assert transitions.commands[0]["request_fingerprint"] == fingerprint
    assert authorization.calls == [(1001, "primary")]


@pytest.mark.asyncio
async def test_rejection_passes_only_normalized_reason_to_boundary() -> None:
    order = Order(uuid4(), "ORD-REVIEW02", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    service = AdminOrderReviewService(transitions, FakeAdminAuthorization())
    fingerprint = AdminOrderReviewService.review_fingerprint(
        order.internal_order_id, 1, 1001, "primary", "reject", "payment mismatch", "review-reject-1"
    )

    await service.review(AdminReviewOrderCommand(
        internal_order_id=order.internal_order_id,
        actor_telegram_user_id=1001,
        actor_type="primary",
        expected_version=1,
        action="reject",
        reason="  payment   mismatch  ",
        idempotency_key="review-reject-1",
        session_id=uuid4(),
        confirmation_id=uuid4(),
        request_fingerprint=fingerprint,
    ))

    assert transitions.commands[0]["event_payload"] == {"reason": "payment mismatch"}


@pytest.mark.asyncio
async def test_review_requires_a_session() -> None:
    order = Order(uuid4(), "ORD-REVIEW00", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    service = AdminOrderReviewService(transitions, FakeAdminAuthorization())

    with pytest.raises(ValueError, match="recent admin session"):
        await service.review(AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=1001,
            actor_type="primary",
            expected_version=1,
            action="approve",
            idempotency_key="review-session-required",
        ))

    assert transitions.commands == []


@pytest.mark.asyncio
async def test_review_requires_confirmation() -> None:
    order = Order(uuid4(), "ORD-REVIEW06", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    service = AdminOrderReviewService(transitions, FakeAdminAuthorization())

    with pytest.raises(ValueError, match="confirmation"):
        await service.review(AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=1001,
            actor_type="primary",
            expected_version=1,
            action="approve",
            idempotency_key="review-confirmation-required",
            session_id=uuid4(),
        ))

    assert transitions.commands == []


@pytest.mark.asyncio
async def test_rejection_requires_a_reason() -> None:
    order = Order(uuid4(), "ORD-REVIEW03", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    service = AdminOrderReviewService(transitions, FakeAdminAuthorization())

    with pytest.raises(ValueError, match="review reason"):
        await service.review(AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=1001,
            actor_type="primary",
            expected_version=1,
            action="reject",
            reason="no",
            idempotency_key="review-reject-short",
            session_id=uuid4(),
            confirmation_id=uuid4(),
            request_fingerprint="0" * 64,
        ))

    assert transitions.commands == []


@pytest.mark.asyncio
async def test_invalid_actor_type_is_rejected_before_authorization() -> None:
    order = Order(uuid4(), "ORD-REVIEW04", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization()
    service = AdminOrderReviewService(transitions, authorization)

    with pytest.raises(ValueError, match="admin actor type"):
        await service.review(AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=1001,
            actor_type="customer",
            expected_version=1,
            action="approve",
            idempotency_key="review-invalid-actor",
            session_id=uuid4(),
            confirmation_id=uuid4(),
            request_fingerprint="0" * 64,
        ))

    assert transitions.commands == []
    assert authorization.calls == []


@pytest.mark.asyncio
async def test_unauthorized_admin_cannot_transition_order() -> None:
    order = Order(uuid4(), "ORD-REVIEW05", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization(authorized=False)
    service = AdminOrderReviewService(transitions, authorization)
    fingerprint = AdminOrderReviewService.review_fingerprint(
        order.internal_order_id, 1, 9999, "primary", "approve", None, "review-unauthorized"
    )

    with pytest.raises(PermissionError, match="not authorized"):
        await service.review(AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=9999,
            actor_type="primary",
            expected_version=1,
            action="approve",
            idempotency_key="review-unauthorized",
            session_id=uuid4(),
            confirmation_id=uuid4(),
            request_fingerprint=fingerprint,
        ))

    assert transitions.commands == []
    assert order.status is OrderStatus.UNDER_REVIEW
