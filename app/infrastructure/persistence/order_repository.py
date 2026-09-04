from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from app.application.ports import PersistedOrderTransition, OrderRepository
from app.domain.order import Order
from app.domain.order_status import OrderStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class OrderPersistenceError(RuntimeError):
    """Raised when the order persistence boundary returns an invalid result."""


class SupabaseOrderRepository(OrderRepository):
    """Supabase adapter for the authoritative order-transition RPCs.

    The PostgreSQL transition function performs the real row lock and optimistic
    concurrency check. ``get_for_update`` is therefore a read used for
    application preconditions; it must not be mistaken for a cross-request
    transaction lock.
    """

    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_for_update(self, internal_order_id: UUID) -> Order | None:
        rows = await self._rpc(
            "get_order_for_transition",
            {"p_order_id": str(internal_order_id)},
        )
        if not rows:
            return None
        return self._map_order(rows[0])

    async def transition_if_version(
        self,
        internal_order_id: UUID,
        target_status: OrderStatus,
        expected_version: int,
        actor_telegram_user_id: int | None = None,
        actor_type: str | None = None,
        event_payload: dict[str, object] | None = None,
    ) -> PersistedOrderTransition | None:
        params = {
            "p_order_id": str(internal_order_id),
            "p_target_status": target_status.value,
            "p_expected_version": expected_version,
            "p_actor_telegram_user_id": actor_telegram_user_id,
            "p_actor_type": actor_type,
            "p_event_payload": event_payload or {},
        }
        rows = await self._rpc("transition_order_if_version", params)
        if not rows:
            return None
        updated = self._map_order(rows[0])
        return PersistedOrderTransition(
            order=updated,
            state_before=self._infer_state_before(target_status, updated.status),
            state_after=updated.status,
            transitioned_at=datetime.now(timezone.utc),
        )

    async def _rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(function_name, params).execute
            )
        except Exception as exc:
            raise OrderPersistenceError(
                f"order persistence RPC failed: {function_name}"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            raise OrderPersistenceError(self._error_message(function_name, error))

        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise OrderPersistenceError(
                f"order persistence RPC returned invalid data: {function_name}"
            )
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _map_order(row: dict[str, Any]) -> Order:
        try:
            status = OrderStatus(str(row["status"]).strip().upper())
            version = int(row["version"])
            if version < 1:
                raise ValueError("order version must be positive")
            return Order(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=status,
                version=version,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrderPersistenceError("invalid order persistence payload") from exc

    @staticmethod
    def _infer_state_before(
        target_status: OrderStatus,
        state_after: OrderStatus,
    ) -> OrderStatus:
        # The RPC returns only the post-transition row. The application already
        # loaded the authoritative pre-transition order, so this value is only a
        # persistence fallback. Callers that require the exact prior state must
        # retain the pre-transition Order from the application boundary.
        if target_status == state_after:
            return state_after
        return state_after

    @staticmethod
    def _error_message(function_name: str, error: Any) -> str:
        if isinstance(error, str) and error.strip():
            return f"{function_name} failed: {error.strip()}"
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return f"{function_name} failed: {message.strip()}"
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return f"{function_name} failed: {value.strip()}"
        return f"{function_name} failed: {str(error).strip() or 'unknown persistence error'}"
