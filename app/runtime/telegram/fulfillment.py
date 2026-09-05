from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.fulfillment import FulfillmentService
FULFILLMENT_ERROR_MESSAGE = "fulfillment operation could not be completed"


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class FulfillmentApplication(Protocol):
    async def claim(self, **kwargs: object): ...
    async def complete(self, **kwargs: object): ...


class TelegramFulfillmentHandler:
    """Framework-neutral adapter; Telegram parsing/authentication stays outside this boundary."""

    def __init__(self, service: FulfillmentService) -> None:
        self._service = service

    async def claim(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="claim")

    async def complete(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="complete")

    async def _run(self, request: TelegramFulfillmentInput, operation: str) -> TelegramFulfillmentResponse:
        if (
            not isinstance(request.admin_user_id, int)
            or request.admin_user_id <= 0
            or not isinstance(request.expected_version, int)
            or request.expected_version < 1
            or not isinstance(request.order_id, UUID)
            or not isinstance(request.actor_type, str)
            or not isinstance(request.idempotency_key, str)
        ):
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        actor_type = request.actor_type.strip().lower()
        idempotency_key = request.idempotency_key.strip()
        if actor_type not in {"primary", "backup"} or not 1 <= len(idempotency_key) <= 128:
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                internal_order_id=request.order_id,
                expected_version=request.expected_version,
                admin_telegram_user_id=request.admin_user_id,
                actor_type=actor_type,
                idempotency_key=idempotency_key,
            )
        except ValueError:
            return TelegramFulfillmentResponse(
                False,
                None,
                None,
                False,
                FULFILLMENT_ERROR_MESSAGE,
            )
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramFulfillmentResponse(
                False, None, None, False, FULFILLMENT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, "fulfillment operation failed")
        return TelegramFulfillmentResponse(True, result.status, result.version, result.replayed, "fulfillment operation accepted")
