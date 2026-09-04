from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.order_service import OrderTransitionService
from app.application.ports import PersistedOrderTransition
from app.application.uow import UnitOfWork
from app.domain.order import Order
from app.domain.order_status import OrderStatus
from app.domain.order_transition import OrderTransitionCommand


class FakeOrderRepository:
    def __init__(self, order: Order) -> None:
        self.order = order
        self.transition_calls = 0
        self.actor = None
        self.event_payload = None

    async def get_for_update(self, internal_order_id):
        return self.order if internal_order_id == self.order.internal_order_id else None

    async def transition_if_version(
        self,
        internal_order_id,
        target_status,
        expected_version,
        actor_telegram_user_id=None,
        actor_type=None,
        event_payload=None,
    ):
        self.transition_calls += 1
        self.actor = (actor_telegram_user_id, actor_type)
        self.event_payload = event_payload
        if self.order.version != expected_version:
            return None
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


class FakeIdempotencyRepository:
    def __init__(self) -> None:
        self.results = {}

    async def get_result(self, key):
        return self.results.get(key)

    async def store_result(self, key, result):
        self.results[key] = result


class FakeUnitOfWork:
    def __init__(self, orders: FakeOrderRepository, idempotency: FakeIdempotencyRepository) -> None:
        self.orders = orders
        self.idempotency = idempotency
        self.commit_calls = 0
        self.rollback_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_repeated_approval_is_idempotent() -> None:
    order = Order(uuid4(), "ORD-TEST01", OrderStatus.UNDER_REVIEW, 1)
    orders = FakeOrderRepository(order)
    idem = FakeIdempotencyRepository()
    uow: UnitOfWork = FakeUnitOfWork(orders, idem)
    service = OrderTransitionService(uow)

    command = OrderTransitionCommand(
        order.internal_order_id,
        OrderStatus.APPROVED,
        123,
        "primary",
        None,
        1,
        "approve-1",
    )

    first = await service.transition_order(command)
    second = await service.transition_order(command)

    assert first is second
    assert orders.transition_calls == 1
    assert orders.order.status is OrderStatus.APPROVED
    assert orders.actor == (123, "primary")
    assert orders.event_payload is None
    assert uow.commit_calls == 1


@pytest.mark.asyncio
async def test_transition_propagates_reason_to_persistence_event() -> None:
    order = Order(uuid4(), "ORD-TEST03", OrderStatus.UNDER_REVIEW, 2)
    orders = FakeOrderRepository(order)
    idem = FakeIdempotencyRepository()
    uow: UnitOfWork = FakeUnitOfWork(orders, idem)
    service = OrderTransitionService(uow)

    command = OrderTransitionCommand(
        order.internal_order_id,
        OrderStatus.REJECTED,
        456,
        "primary",
        "receipt mismatch",
        2,
        "reject-1",
    )

    await service.transition_order(command)

    assert orders.actor == (456, "primary")
    assert orders.event_payload == {"reason": "receipt mismatch"}


@pytest.mark.asyncio
async def test_stale_expected_version_blocks_transition() -> None:
    order = Order(uuid4(), "ORD-TEST02", OrderStatus.UNDER_REVIEW, 4)
    orders = FakeOrderRepository(order)
    idem = FakeIdempotencyRepository()
    uow: UnitOfWork = FakeUnitOfWork(orders, idem)
    service = OrderTransitionService(uow)

    command = OrderTransitionCommand(
        order.internal_order_id,
        OrderStatus.APPROVED,
        123,
        "primary",
        None,
        3,
        "approve-stale",
    )

    with pytest.raises(RuntimeError, match="stale order version"):
        await service.transition_order(command)

    assert orders.transition_calls == 0
    assert orders.order.status is OrderStatus.UNDER_REVIEW
    assert orders.order.version == 4
    assert uow.rollback_calls == 1
