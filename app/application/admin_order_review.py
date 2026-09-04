from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.order_service import OrderTransitionService
from app.application.ports import PersistedOrderTransition
from app.domain.order_status import OrderStatus
from app.domain.order_transition import OrderTransitionCommand


MIN_REASON_LENGTH = 5
MAX_REASON_LENGTH = 1000
ADMIN_ACTOR_TYPES = frozenset({"primary", "backup"})


@dataclass(frozen=True, slots=True)
class AdminReviewOrderCommand:
    internal_order_id: UUID
    actor_telegram_user_id: int
    actor_type: str
    expected_version: int
    action: str
    reason: str | None = None
    idempotency_key: str = ""


class AdminOrderReviewService:
    """Application boundary for human admin review of a submitted payment."""

    def __init__(self, transitions: OrderTransitionService) -> None:
        self._transitions = transitions

    async def review(self, command: AdminReviewOrderCommand) -> PersistedOrderTransition:
        if command.actor_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        actor_type = command.actor_type.strip().lower()
        if actor_type not in ADMIN_ACTOR_TYPES:
            raise ValueError("unsupported admin actor type")
        if command.expected_version < 1:
            raise ValueError("expected version must be positive")

        action = command.action.strip().lower()
        targets = {
            "approve": OrderStatus.APPROVED,
            "reject": OrderStatus.REJECTED,
            "clarify": OrderStatus.CLARIFICATION_REQUIRED,
        }
        target = targets.get(action)
        if target is None:
            raise ValueError("unsupported admin review action")

        reason = " ".join((command.reason or "").split())
        if target in {OrderStatus.REJECTED, OrderStatus.CLARIFICATION_REQUIRED}:
            if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
                raise ValueError(
                    f"review reason must be between {MIN_REASON_LENGTH} and {MAX_REASON_LENGTH} characters"
                )
        else:
            reason = None

        if not command.idempotency_key.strip():
            raise ValueError("idempotency key is required")

        transition = OrderTransitionCommand(
            internal_order_id=command.internal_order_id,
            target_status=target,
            actor_id=command.actor_telegram_user_id,
            actor_type=actor_type,
            reason=reason,
            expected_version=command.expected_version,
            idempotency_key=command.idempotency_key.strip(),
        )
        return await self._transitions.transition_order(transition)
