from __future__ import annotations

from datetime import datetime, timezone

from app.application.ports import PersistedOrderTransition
from app.application.uow import UnitOfWork
from app.domain.order_transition import OrderTransitionCommand, validate_transition_command


class OrderTransitionService:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._uow = unit_of_work

    async def transition_order(
        self,
        command: OrderTransitionCommand,
    ) -> PersistedOrderTransition:
        async with self._uow:
            existing = await self._uow.idempotency.get_result(command.idempotency_key)
            if existing is not None:
                return existing

            order = await self._uow.orders.get_for_update(command.internal_order_id)
            if order is None:
                raise LookupError(f"order not found: {command.internal_order_id}")

            if order.version != command.expected_version:
                raise RuntimeError(
                    f"stale order version: expected {command.expected_version}, current {order.version}"
                )

            validate_transition_command(order.status, command)
            state_before = order.status

            if command.target_status == state_before:
                result = PersistedOrderTransition(
                    order=order,
                    state_before=state_before,
                    state_after=state_before,
                    transitioned_at=datetime.now(timezone.utc),
                )
                await self._uow.idempotency.store_result(command.idempotency_key, result)
                await self._uow.commit()
                return result

            persisted = await self._uow.orders.transition_if_version(
                command.internal_order_id,
                command.target_status,
                command.expected_version,
                actor_telegram_user_id=command.actor_id,
                actor_type=command.actor_type,
                event_payload={"reason": command.reason} if command.reason else None,
            )
            if persisted is None:
                raise RuntimeError("order changed concurrently; transition was not applied")

            # PostgreSQL is authoritative for the resulting state/version, while
            # this application snapshot is authoritative for the pre-state that
            # was validated immediately before the atomic transition call.
            result = PersistedOrderTransition(
                order=persisted.order,
                state_before=state_before,
                state_after=persisted.state_after,
                transitioned_at=persisted.transitioned_at,
            )
            await self._uow.idempotency.store_result(command.idempotency_key, result)
            await self._uow.commit()
            return result
