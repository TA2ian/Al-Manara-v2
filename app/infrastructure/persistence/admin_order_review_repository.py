from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.ports import PersistedOrderTransition
from app.domain.order import Order
from app.domain.order_status import OrderStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminOrderReviewPersistenceError(RuntimeError):
    """Raised when the dedicated admin-review persistence boundary is invalid."""


class SupabaseAdminOrderReviewRepository:
    """Authoritative DB boundary for human admin review transitions."""

    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def transition(
        self,
        internal_order_id: UUID,
        target_status: OrderStatus,
        expected_version: int,
        actor_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        event_payload: dict[str, object] | None,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
    ) -> PersistedOrderTransition:
        rows = await self._rpc(
            {
                "p_order_id": str(internal_order_id),
                "p_target_status": target_status.value,
                "p_expected_version": expected_version,
                "p_admin_telegram_user_id": actor_telegram_user_id,
                "p_actor_type": actor_type,
                "p_idempotency_key": idempotency_key.strip(),
                "p_event_payload": event_payload or {},
                "p_session_id": str(session_id),
                "p_confirmation_id": str(confirmation_id),
                "p_request_fingerprint": request_fingerprint,
            }
        )
        if not rows:
            raise AdminOrderReviewPersistenceError("admin review RPC returned no transition")

        row = rows[0]
        try:
            order = Order(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=OrderStatus(str(row["status"]).strip().upper()),
                version=int(row["version"]),
            )
            if order.version < 1:
                raise ValueError("order version must be positive")
            state_before = OrderStatus(str(row["state_before"]).strip().upper())
            state_after = OrderStatus(str(row["state_after"]).strip().upper())
            transitioned_at = self._parse_datetime(row["transitioned_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminOrderReviewPersistenceError("invalid admin review RPC payload") from exc

        if order.internal_order_id != internal_order_id or state_after is not order.status:
            raise AdminOrderReviewPersistenceError("admin review RPC returned inconsistent order state")

        return PersistedOrderTransition(
            order=order,
            state_before=state_before,
            state_after=state_after,
            transitioned_at=transitioned_at,
        )

    async def _rpc(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(
                self._client.rpc("admin_review_order_transition_idempotent", params).execute
            )
        except Exception as exc:
            raise AdminOrderReviewPersistenceError("admin review persistence RPC failed") from exc

        error = getattr(response, "error", None)
        if error:
            raise AdminOrderReviewPersistenceError(self._error_message(error))

        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminOrderReviewPersistenceError("admin review RPC returned invalid data")
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("invalid transition timestamp")
        if result.tzinfo is None:
            raise ValueError("transition timestamp must be timezone-aware")
        return result

    @staticmethod
    def _error_message(error: Any) -> str:
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(error).strip() or "unknown persistence error"
