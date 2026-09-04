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

            if command.target_status == order.status:
                result = PersistedOrderTransition(
                    order=order,
                    state_before=order.status,
                    state_after=order.status,
                    transitioned_at=datetime.now(timezone.utc),
                )
                await self._uow.idempotency.store_result(command.idempotency_key, result)
                await self._uow.commit()
                return result

            result = await self._uow.orders.transition_if_version(
                command.internal_order_id,
                command.target_status,
                command.expected_version,
                actor_telegram_user_id=command.actor_id,
                actor_type=command.actor_type,
                event_payload={"reason": command.reason} if command.reason else None,
            )
            if result is None:
                raise RuntimeError("order changed concurrently; transition was not applied")

            # The repository RPC returns the post-transition row. Preserve the
            # exact pre-transition state captured before the atomic DB mutation.
            result = PersistedOrderTransition(
                order=result.order,
                state_before=order.status,
                state_after=result.state_after,
                transitioned_at=result.transitioned_at,
            )
            await self._uow.idempotency.store_result(command.idempotency_key, result)
            await self._uow.commit()
            return result
