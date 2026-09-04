from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.admin_order_closure import (
    AdminOrderClosureCommand,
    AdminOrderClosureService,
)


@dataclass(frozen=True, slots=True)
class TelegramAdminClosureInput:
    admin_user_id: int
    order_id: UUID
    expected_version: int
    session_id: UUID
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramAdminClosureResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class TelegramAdminOrderClosureHandler:
    """Framework-neutral adapter for the privileged no-fulfillment closure."""

    def __init__(self, service: AdminOrderClosureService) -> None:
        self._service = service

    async def handle(
        self, request: TelegramAdminClosureInput
    ) -> TelegramAdminClosureResponse:
        if request.admin_user_id <= 0 or request.expected_version < 1:
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        if not request.reason.strip() or not request.idempotency_key.strip():
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        try:
            result = await self._service.close_without_fulfillment(
                AdminOrderClosureCommand(
                    internal_order_id=request.order_id,
                    admin_telegram_user_id=request.admin_user_id,
                    expected_version=request.expected_version,
                    session_id=request.session_id,
                    reason=request.reason,
                    idempotency_key=request.idempotency_key,
                )
            )
        except ValueError as exc:
            return TelegramAdminClosureResponse(False, None, None, False, str(exc))
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramAdminClosureResponse(
                False, None, None, False, "The order could not be closed. Please retry."
            )
        except Exception:
            return TelegramAdminClosureResponse(False, None, None, False, "The closure operation failed.")

        return TelegramAdminClosureResponse(
            True,
            result.status,
            result.version,
            result.replayed,
            "Order closed without fulfillment.",
        )
