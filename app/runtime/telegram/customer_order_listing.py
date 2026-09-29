from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.customer_order_listing import (
    CustomerOrderListingService,
    CustomerOrderPage,
    ListCustomerOrdersCommand,
)
ORDER_LISTING_RETRY_MESSAGE = "Orders could not be loaded. Please retry."


@dataclass(frozen=True, slots=True)
class TelegramCustomerOrderListingInput:
    """Transport input built from Telegram's authenticated update sender.

    Callback data may select a page, but never the customer identity.
    """

    authenticated_telegram_user_id: int
    page: int = 0
    page_size: int = 5


@dataclass(frozen=True, slots=True)
class TelegramCustomerOrderListingResponse:
    ok: bool
    page: CustomerOrderPage | None = None
    message: str = ""


class CustomerOrderListingApplication(Protocol):
    async def list(self, command: ListCustomerOrdersCommand) -> CustomerOrderPage: ...


class TelegramCustomerOrderListingHandler:
    def __init__(
        self, service: CustomerOrderListingApplication | CustomerOrderListingService
    ) -> None:
        self._service = service

    async def handle(
        self, request: TelegramCustomerOrderListingInput
    ) -> TelegramCustomerOrderListingResponse:
        if request.authenticated_telegram_user_id <= 0:
            return TelegramCustomerOrderListingResponse(
                False, message="Invalid customer identity."
            )
        if request.page < 0:
            return TelegramCustomerOrderListingResponse(
                False, message="The page is invalid."
            )
        if request.page_size < 1 or request.page_size > 50:
            return TelegramCustomerOrderListingResponse(
                False, message="The page size is invalid."
            )
        try:
            result = await self._service.list(
                ListCustomerOrdersCommand(
                    customer_telegram_user_id=request.authenticated_telegram_user_id,
                    page=request.page,
                    page_size=request.page_size,
                )
            )
        except ValueError:
            return TelegramCustomerOrderListingResponse(
                False, message=ORDER_LISTING_RETRY_MESSAGE
            )
        except RuntimeError:
            return TelegramCustomerOrderListingResponse(
                False, message=ORDER_LISTING_RETRY_MESSAGE
            )
        except Exception:
            return TelegramCustomerOrderListingResponse(
                False, message="An unexpected error occurred. Please retry."
            )
        return TelegramCustomerOrderListingResponse(
            True, page=result, message="Orders loaded."
        )