from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.admin_order_review import AdminOrderReviewService, AdminReviewOrderCommand
from app.application.ports import PersistedOrderTransition

REVIEW_ERROR_MESSAGE = "The order could not be updated. Please retry."


class AdminActorTypeResolver(Protocol):
    async def resolve_actor_type(self, telegram_user_id: int) -> str | None: ...


class AdminSessionValidator(Protocol):
    async def validate_session(self, telegram_user_id: int, actor_type: str, session_id: UUID) -> bool: ...


@dataclass(frozen=True, slots=True)
class TelegramAdminReviewInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    action: str
    reason: str | None = None
    idempotency_key: str = ""
    session_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TelegramAdminReviewResponse:
    ok: bool
    state_after: str | None = None
    message: str = ""


class AdminReviewApplication(Protocol):
    async def review(self, command: AdminReviewOrderCommand) -> PersistedOrderTransition: ...


class TelegramAdminOrderReviewHandler:
    """Framework-neutral adapter for Telegram admin order review."""

    def __init__(
        self,
        service: AdminReviewApplication | AdminOrderReviewService,
        actor_type_resolver: AdminActorTypeResolver | None = None,
        session_validator: AdminSessionValidator | None = None,
    ) -> None:
        self._service = service
        self._actor_type_resolver = actor_type_resolver
        self._session_validator = session_validator

    async def handle(self, request: TelegramAdminReviewInput) -> TelegramAdminReviewResponse:
        if request.admin_user_id <= 0:
            return TelegramAdminReviewResponse(False, message="Invalid administrator identity.")
        if request.expected_version < 1:
            return TelegramAdminReviewResponse(False, message="The order version is invalid.")
        if not request.idempotency_key.strip():
            return TelegramAdminReviewResponse(False, message="A request identifier is required.")
        if not request.action.strip():
            return TelegramAdminReviewResponse(False, message="A review action is required.")
        if not isinstance(request.session_id, UUID):
            return TelegramAdminReviewResponse(False, message="A recent admin session is required.")

        actor_type = request.actor_type
        if self._actor_type_resolver is not None:
            try:
                resolved = await self._actor_type_resolver.resolve_actor_type(request.admin_user_id)
            except Exception:
                return TelegramAdminReviewResponse(False, message=REVIEW_ERROR_MESSAGE)
            if resolved is None:
                return TelegramAdminReviewResponse(False, message="You are not authorized to review orders.")
            actor_type = resolved

        if self._session_validator is not None:
            try:
                valid = await self._session_validator.validate_session(
                    request.admin_user_id, actor_type, request.session_id
                )
            except Exception:
                return TelegramAdminReviewResponse(False, message=REVIEW_ERROR_MESSAGE)
            if not valid:
                return TelegramAdminReviewResponse(False, message="The admin session is no longer valid. Please retry.")

        try:
            result = await self._service.review(
                AdminReviewOrderCommand(
                    internal_order_id=request.order_id,
                    actor_telegram_user_id=request.admin_user_id,
                    actor_type=actor_type,
                    expected_version=request.expected_version,
                    action=request.action,
                    reason=request.reason,
                    idempotency_key=request.idempotency_key,
                )
            )
        except ValueError:
            return TelegramAdminReviewResponse(False, message=REVIEW_ERROR_MESSAGE)
        except PermissionError:
            return TelegramAdminReviewResponse(False, message="You are not authorized to review orders.")
        except LookupError:
            return TelegramAdminReviewResponse(False, message="The requested order was not found.")
        except RuntimeError:
            return TelegramAdminReviewResponse(False, message=REVIEW_ERROR_MESSAGE)
        except Exception:
            return TelegramAdminReviewResponse(False, message="An unexpected error occurred. Please retry.")

        return TelegramAdminReviewResponse(
            True,
            state_after=result.state_after.value,
            message=f"Order review completed: {result.state_after.value}.",
        )
