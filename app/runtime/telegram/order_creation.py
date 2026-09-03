from __future__ import annotations

from app.application.create_purchase_order import (
    CreatePurchaseOrderCommand,
    CreatePurchaseOrderService,
)
from app.runtime.telegram.contracts import (
    TelegramOrderInput,
    TelegramOrderMessages,
    TelegramOrderResponse,
)


class TelegramOrderCreationHandler:
    """Thin Telegram-facing adapter; business rules remain in the application/domain layers."""

    def __init__(self, service: CreatePurchaseOrderService) -> None:
        self._service = service

    async def handle(self, request: TelegramOrderInput) -> TelegramOrderResponse:
        command = CreatePurchaseOrderCommand(
            user_id=request.user_id,
            wallet_id=request.wallet_id,
            network_code=request.network_code,
            requested_amount=request.requested_amount,
            payment_currency=request.payment_currency,
            idempotency_key=request.idempotency_key,
        )
        try:
            result = await self._service.create(command)
        except ValueError as exc:
            message = str(exc)
            if "payment identity" in message:
                return TelegramOrderResponse(False, TelegramOrderMessages.NOT_VERIFIED)
            if "network" in message:
                return TelegramOrderResponse(False, TelegramOrderMessages.NETWORK_UNAVAILABLE)
            if "idempotency" in message or "currency" in message:
                return TelegramOrderResponse(False, TelegramOrderMessages.INVALID_INPUT)
            return TelegramOrderResponse(False, TelegramOrderMessages.INVALID_INPUT)
        except LookupError:
            return TelegramOrderResponse(False, TelegramOrderMessages.WALLET_NOT_AVAILABLE)
        except RuntimeError as exc:
            message = str(exc)
            if "concurrently" in message or "stale" in message:
                return TelegramOrderResponse(False, TelegramOrderMessages.CONFLICT)
            return TelegramOrderResponse(False, TelegramOrderMessages.CONFIGURATION_ERROR)

        order_code = getattr(result, "public_order_code", None)
        if not order_code:
            raise RuntimeError("order creation returned an invalid persistence result")
        return TelegramOrderResponse(
            True,
            TelegramOrderMessages.CREATED.format(order_code=order_code),
            order_code,
        )
