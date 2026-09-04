from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.create_purchase_order import CreatePurchaseOrderCommand
from app.runtime.telegram.contracts import (
    TelegramOrderInput,
    TelegramOrderMessages,
    TelegramOrderResponse,
)


class OrderCreationService(Protocol):
    async def create(self, command: CreatePurchaseOrderCommand) -> object: ...


@dataclass(frozen=True, slots=True)
class TelegramOrderCreationHandler:
    """Framework-neutral Telegram adapter for customer order creation."""

    service: OrderCreationService

    async def handle(self, data: TelegramOrderInput) -> TelegramOrderResponse:
        try:
            result = await self.service.create(
                CreatePurchaseOrderCommand(
                    user_id=data.user_id,
                    wallet_id=data.wallet_id,
                    network_code=data.network_code,
                    requested_amount=data.requested_amount,
                    payment_currency=data.payment_currency,
                    idempotency_key=data.idempotency_key,
                )
            )
        except ValueError as exc:
            message = str(exc)
            if "payment identity" in message:
                return TelegramOrderResponse(False, TelegramOrderMessages.NOT_VERIFIED)
            if "network" in message or "network" in message.lower():
                return TelegramOrderResponse(False, TelegramOrderMessages.NETWORK_UNAVAILABLE)
            return TelegramOrderResponse(False, TelegramOrderMessages.INVALID_INPUT)
        except LookupError:
            return TelegramOrderResponse(False, TelegramOrderMessages.WALLET_NOT_AVAILABLE)
        except (RuntimeError, OSError):
            return TelegramOrderResponse(False, TelegramOrderMessages.CONFIGURATION_ERROR)
        except Exception:
            # The transport boundary must never expose internal exception details.
            return TelegramOrderResponse(False, TelegramOrderMessages.CONFIGURATION_ERROR)

        order_code = getattr(result, "public_order_code", None)
        if order_code is None:
            order_code = getattr(result, "order_code", None)
        if not order_code:
            return TelegramOrderResponse(False, TelegramOrderMessages.CONFIGURATION_ERROR)
        return TelegramOrderResponse(
            True,
            TelegramOrderMessages.CREATED.format(order_code=order_code),
            str(order_code),
        )
