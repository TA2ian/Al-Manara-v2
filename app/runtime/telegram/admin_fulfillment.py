from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.fulfillment import FulfillmentService


@dataclass(frozen=True, slots=True)
class TelegramAdminFulfillmentInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramAdminFulfillmentResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class TelegramAdminFulfillmentHandler:
    """Framework-neutral adapter for the claim/complete fulfillment lifecycle."""

    def __init__(self, service: FulfillmentService) -> None:
        self._service = service

    async def claim(
        self, request: TelegramAdminFulfillmentInput
    ) -> TelegramAdminFulfillmentResponse:
        return await self._execute(request, operation="claim")

    async def complete(
        self, request: TelegramAdminFulfillmentInput
    ) -> TelegramAdminFulfillmentResponse:
        return await self._execute(request, operation="complete")

    async def _execute(
        self, request: TelegramAdminFulfillmentInput, *, operation: str
    ) -> TelegramAdminFulfillmentResponse:
        if (
            not isinstance(request.admin_user_id, int)
            or request.admin_user_id <= 0
            or not isinstance(request.expected_version, int)
            or request.expected_version < 1
            or not isinstance(request.actor_type, str)
            or not isinstance(request.idempotency_key, str)
            or not request.actor_type.strip()
            or not request.idempotency_key.strip()
            or not isinstance(request.order_id, UUID)
        ):
            return TelegramAdminFulfillmentResponse(
                False, None, None, False, "invalid fulfillment request"
            )

        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                request.order_id,
                request.expected_version,
                request.admin_user_id,
                request.actor_type,
                request.idempotency_key,
            )
        except ValueError as exc:
            return TelegramAdminFulfillmentResponse(False, None, None, False, str(exc))
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramAdminFulfillmentResponse(
                False,
                None,
                None,
                False,
                "The fulfillment operation could not be completed. Please retry.",
            )
        except Exception:
            return TelegramAdminFulfillmentResponse(
                False, None, None, False, "The fulfillment operation failed."
            )

        message = (
            "Order fulfillment claimed."
            if operation == "claim"
            else "Order fulfillment completed."
        )
        return TelegramAdminFulfillmentResponse(
            True, result.status, result.version, result.replayed, message
        )
