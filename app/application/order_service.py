from __future__ import annotations

from app.application.ports import IdempotencyRepository, OrderRepository, PersistedOrderTransition
from app.domain.order_transition import OrderTransitionCommand, validate_transition_command


class OrderTransitionService:
    def __init__(
        self,
        order_repository: OrderRepository,
        idempotency_repository: IdempotencyRepository,
    ) -> None:
        self._orders = order_repository
        self._idempotency = idempotency_repository

    async def transition_order(
        self,
        command: OrderTransitionCommand,
    ) -> PersistedOrderTransition:
        existing = await self._idempotency.get_result(command.idempotency_key)
        if existing is not None:
            return existing

        order = await self._orders.get_for_update(command.internal_order_id)
        if order is None:
            raise LookupError(f"order not found: {command.internal_order_id}")

        if order.version != command.expected_version:
            raise RuntimeError(
                f"stale order version: expected {command.expected_version}, current {order.version}"
            )

        validate_transition_command(order.status, command)
        if command.target_status == order.status:
            result = PersistedOrderTransition(
                order=order,
                state_before=order.status,
                state_after=order.status,
                transitioned_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
            await self._idempotency.store_result(command.idempotency_key, result)
            return result

        result = await self._orders.transition_if_version(
            command.internal_order_id,
            command.target_status,
            command.expected_version,
        )
        if result is None:
            raise RuntimeError("order changed concurrently; transition was not applied")

        await self._idempotency.store_result(command.idempotency_key, result)
        return result
