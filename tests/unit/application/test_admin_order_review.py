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

    async def transition_order(self, command):
        self.commands.append(command)
        state_before = self.order.status
        updated = self.order.transition_to(command.target_status)
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
async def test_admin_approval_targets_approved_state() -> None:
    order = Order(uuid4(), "ORD-REVIEW01", OrderStatus.UNDER_REVIEW, 2)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization()
    service = AdminOrderReviewService(transitions, authorization)

    result = await service.review(
        AdminReviewOrderCommand(
            internal_order_id=order.internal_order_id,
            actor_telegram_user_id=1001,
            actor_type="primary",
            expected_version=2,
            action="approve",
            idempotency_key="review-approve-1",
        )
    )

    assert result.state_after is OrderStatus.APPROVED
    assert transitions.commands[0].reason is None
    assert authorization.calls == [(1001, "primary")]


@pytest.mark.asyncio
async def test_rejection_requires_a_reason() -> None:
    order = Order(uuid4(), "ORD-REVIEW02", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    service = AdminOrderReviewService(transitions, FakeAdminAuthorization())

    with pytest.raises(ValueError, match="review reason"):
        await service.review(
            AdminReviewOrderCommand(
                internal_order_id=order.internal_order_id,
                actor_telegram_user_id=1001,
                actor_type="primary",
                expected_version=1,
                action="reject",
                reason="no",
                idempotency_key="review-reject-1",
            )
        )

    assert transitions.commands == []


@pytest.mark.asyncio
async def test_invalid_actor_type_is_rejected_before_authorization() -> None:
    order = Order(uuid4(), "ORD-REVIEW03", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization()
    service = AdminOrderReviewService(transitions, authorization)

    with pytest.raises(ValueError, match="admin actor type"):
        await service.review(
            AdminReviewOrderCommand(
                internal_order_id=order.internal_order_id,
                actor_telegram_user_id=1001,
                actor_type="customer",
                expected_version=1,
                action="approve",
                idempotency_key="review-invalid-actor",
            )
        )

    assert transitions.commands == []
    assert authorization.calls == []


@pytest.mark.asyncio
async def test_unauthorized_admin_cannot_transition_order() -> None:
    order = Order(uuid4(), "ORD-REVIEW04", OrderStatus.UNDER_REVIEW, 1)
    transitions = FakeTransitions(order)
    authorization = FakeAdminAuthorization(authorized=False)
    service = AdminOrderReviewService(transitions, authorization)

    with pytest.raises(PermissionError, match="not authorized"):
        await service.review(
            AdminReviewOrderCommand(
                internal_order_id=order.internal_order_id,
                actor_telegram_user_id=9999,
                actor_type="primary",
                expected_version=1,
                action="approve",
                idempotency_key="review-unauthorized",
            )
        )

    assert transitions.commands == []
    assert order.status is OrderStatus.UNDER_REVIEW
