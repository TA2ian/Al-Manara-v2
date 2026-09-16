from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.ports import PersistedOrderTransition
from app.domain.order_status import OrderStatus

MIN_REASON_LENGTH = 5
MAX_REASON_LENGTH = 1000
ADMIN_ACTOR_TYPES = frozenset({"primary", "backup"})


class AdminAuthorizationPort(Protocol):
    async def authorize(self, telegram_user_id: int, actor_type: str) -> bool: ...


class AdminReviewTransitionPort(Protocol):
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
    ) -> PersistedOrderTransition: ...


@dataclass(frozen=True, slots=True)
class AdminReviewOrderCommand:
    internal_order_id: UUID
    actor_telegram_user_id: int
    actor_type: str
    expected_version: int
    action: str
    reason: str | None = None
    idempotency_key: str = ""
    session_id: UUID | None = None


class AdminOrderReviewService:
    """Application boundary for human admin review of a submitted payment."""

    def __init__(
        self,
        transitions: AdminReviewTransitionPort,
        authorization: AdminAuthorizationPort,
    ) -> None:
        self._transitions = transitions
        self._authorization = authorization

    async def review(self, command: AdminReviewOrderCommand) -> PersistedOrderTransition:
        if not isinstance(command.internal_order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.actor_telegram_user_id, int) or command.actor_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        if not isinstance(command.actor_type, str):
            raise ValueError("admin actor type is required")
        actor_type = command.actor_type.strip().lower()
        if actor_type not in ADMIN_ACTOR_TYPES:
            raise ValueError("unsupported admin actor type")
        if not isinstance(command.expected_version, int) or command.expected_version < 1:
            raise ValueError("expected version must be positive")
        if not isinstance(command.action, str):
            raise ValueError("review action is required")
        if not isinstance(command.idempotency_key, str):
            raise ValueError("idempotency key is required")
        if not isinstance(command.session_id, UUID):
            raise ValueError("recent admin session is required")

        if not await self._authorization.authorize(command.actor_telegram_user_id, actor_type):
            raise PermissionError("admin is not authorized for order review")

        action = command.action.strip().lower()
        targets = {
            "approve": OrderStatus.APPROVED,
            "reject": OrderStatus.REJECTED,
            "clarify": OrderStatus.CLARIFICATION_REQUIRED,
        }
        target = targets.get(action)
        if target is None:
            raise ValueError("unsupported admin review action")

        if command.reason is not None and not isinstance(command.reason, str):
            raise ValueError("review reason is invalid")
        reason = " ".join((command.reason or "").split())
        if target in {OrderStatus.REJECTED, OrderStatus.CLARIFICATION_REQUIRED}:
            if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
                raise ValueError(
                    f"review reason must be between {MIN_REASON_LENGTH} and {MAX_REASON_LENGTH} characters"
                )
        else:
            reason = None

        idempotency_key = command.idempotency_key.strip()
        if not 1 <= len(idempotency_key) <= 128:
            raise ValueError("idempotency key must be between 1 and 128 characters")

        return await self._transitions.transition(
            command.internal_order_id,
            target,
            command.expected_version,
            command.actor_telegram_user_id,
            actor_type,
            idempotency_key,
            {"reason": reason} if reason else None,
            command.session_id,
        )
