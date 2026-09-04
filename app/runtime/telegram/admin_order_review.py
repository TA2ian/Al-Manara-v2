from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.admin_order_review import AdminOrderReviewService, AdminReviewOrderCommand
from app.application.ports import PersistedOrderTransition


@dataclass(frozen=True, slots=True)
class TelegramAdminReviewInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    action: str
    reason: str | None = None
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class TelegramAdminReviewResponse:
    ok: bool
    state_after: str | None = None
    message: str = ""


class AdminReviewApplication(Protocol):
    async def review(self, command: AdminReviewOrderCommand) -> PersistedOrderTransition: ...


class TelegramAdminOrderReviewHandler:
    """Framework-neutral adapter for Telegram admin review callbacks/commands.

    actor_type must come from trusted admin context; it is not an authorization
    mechanism by itself. The application and database authorization boundaries
    remain authoritative.
    """

    def __init__(self, service: AdminReviewApplication | AdminOrderReviewService) -> None:
        self._service = service

    async def handle(self, request: TelegramAdminReviewInput) -> TelegramAdminReviewResponse:
        if request.admin_user_id <= 0:
            return TelegramAdminReviewResponse(False, message="Invalid administrator identity.")
        if request.expected_version < 1:
            return TelegramAdminReviewResponse(False, message="The order version is invalid.")
        if not request.idempotency_key.strip():
            return TelegramAdminReviewResponse(False, message="A request identifier is required.")
        if not request.action.strip():
            return TelegramAdminReviewResponse(False, message="A review action is required.")

        try:
            result = await self._service.review(
                AdminReviewOrderCommand(
                    internal_order_id=request.order_id,
                    actor_telegram_user_id=request.admin_user_id,
                    actor_type=request.actor_type,
                    expected_version=request.expected_version,
                    action=request.action,
                    reason=request.reason,
                    idempotency_key=request.idempotency_key,
                )
            )
        except ValueError as exc:
            return TelegramAdminReviewResponse(False, message=str(exc))
        except PermissionError:
            return TelegramAdminReviewResponse(False, message="You are not authorized to review orders.")
        except LookupError:
            return TelegramAdminReviewResponse(False, message="The requested order was not found.")
        except RuntimeError:
            return TelegramAdminReviewResponse(False, message="The order could not be updated. Please retry.")
        except Exception:
            return TelegramAdminReviewResponse(False, message="An unexpected error occurred. Please retry.")

        return TelegramAdminReviewResponse(
            True,
            state_after=result.state_after.value,
            message=f"Order review completed: {result.state_after.value}.",
        )
