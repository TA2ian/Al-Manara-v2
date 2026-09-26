from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.create_purchase_order import CreatePurchaseOrderCommand
from app.application.quote import PurchaseQuote
from app.runtime.telegram.contracts import TelegramOrderInput, TelegramOrderMessages, TelegramOrderResponse

class OrderCreationService(Protocol):
    async def create(self, command: CreatePurchaseOrderCommand) -> object: ...
    async def preview(self, command: CreatePurchaseOrderCommand) -> PurchaseQuote: ...

@dataclass(frozen=True, slots=True)
class TelegramOrderQuoteResponse:
    ok: bool
    quote: PurchaseQuote | None = None
    text: str = ""

@dataclass(frozen=True, slots=True)
class TelegramOrderCreationHandler:
    """Framework-neutral Telegram adapter for customer order creation."""
    service: OrderCreationService

    @staticmethod
    def _command(data: TelegramOrderInput) -> CreatePurchaseOrderCommand:
        return CreatePurchaseOrderCommand(user_id=data.user_id, wallet_id=data.wallet_id, network_code=data.network_code, requested_amount=data.requested_amount, payment_currency=data.payment_currency, idempotency_key=data.idempotency_key)

    @staticmethod
    def _error(exc: Exception) -> str:
        message = str(exc)
        if "payment identity" in message:
            return TelegramOrderMessages.NOT_VERIFIED
        if "network" in message.lower():
            return TelegramOrderMessages.NETWORK_UNAVAILABLE
        if isinstance(exc, LookupError):
            return TelegramOrderMessages.WALLET_NOT_AVAILABLE
        if isinstance(exc, (RuntimeError, OSError)):
            return TelegramOrderMessages.CONFIGURATION_ERROR
        return TelegramOrderMessages.INVALID_INPUT

    async def preview(self, data: TelegramOrderInput) -> TelegramOrderQuoteResponse:
        try:
            quote = await self.service.preview(self._command(data))
        except Exception as exc:
            return TelegramOrderQuoteResponse(False, text=self._error(exc))
        return TelegramOrderQuoteResponse(True, quote=quote)

    async def handle(self, data: TelegramOrderInput) -> TelegramOrderResponse:
        try:
            result = await self.service.create(self._command(data))
        except Exception as exc:
            return TelegramOrderResponse(False, self._error(exc))
        order_code = getattr(result, "public_order_code", None) or getattr(result, "order_code", None)
        if not order_code:
            return TelegramOrderResponse(False, TelegramOrderMessages.CONFIGURATION_ERROR)
        return TelegramOrderResponse(True, TelegramOrderMessages.CREATED.format(order_code=order_code), str(order_code))
