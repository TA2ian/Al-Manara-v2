from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.fulfillment import FulfillmentService


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
        if request.admin_user_id <= 0 or request.expected_version < 1:
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        if not request.idempotency_key.strip() or len(request.idempotency_key.strip()) > 128:
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        if request.actor_type.strip().lower() not in {"primary", "backup"}:
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                internal_order_id=request.order_id,
                expected_version=request.expected_version,
                admin_telegram_user_id=request.admin_user_id,
                actor_type=request.actor_type,
                idempotency_key=request.idempotency_key,
            )
        except ValueError as exc:
            return TelegramFulfillmentResponse(False, None, None, False, str(exc))
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramFulfillmentResponse(False, None, None, False, "fulfillment operation could not be completed")
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, "fulfillment operation failed")
        return TelegramFulfillmentResponse(True, result.status, result.version, result.replayed, "fulfillment operation accepted")
