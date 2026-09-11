import pytest
from dataclasses import fields

from app.application.customer_order_listing import CustomerOrderPage
from app.runtime.telegram.customer_order_listing import (
    TelegramCustomerOrderListingHandler,
    TelegramCustomerOrderListingInput,
)


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result or CustomerOrderPage((), 0, 5, 0)
        self.error = error
        self.calls = []

    async def list(self, command):
        self.calls.append(command)
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_handler_forwards_customer_identity_and_pagination():
    service = FakeService()
    response = await TelegramCustomerOrderListingHandler(service).handle(
        TelegramCustomerOrderListingInput(123, 1, 10)
    )

    assert response.ok is True
    assert response.page == service.result
    assert service.calls[0].customer_telegram_user_id == 123
    assert service.calls[0].page == 1
    assert service.calls[0].page_size == 10


@pytest.mark.asyncio
async def test_handler_rejects_invalid_paging_without_calling_service():
    service = FakeService()
    response = await TelegramCustomerOrderListingHandler(service).handle(
        TelegramCustomerOrderListingInput(123, -1, 5)
    )

    assert response.ok is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_handler_hides_persistence_error_details():
    service = FakeService(error=RuntimeError("database secret detail"))
    response = await TelegramCustomerOrderListingHandler(service).handle(
        TelegramCustomerOrderListingInput(123)
    )

    assert response.ok is False
    assert response.message == "Orders could not be loaded. Please retry."


@pytest.mark.asyncio
async def test_handler_returns_retry_guidance_for_empty_validation_error():
    service = FakeService(error=ValueError())
    response = await TelegramCustomerOrderListingHandler(service).handle(
        TelegramCustomerOrderListingInput(123)
    )

    assert response.ok is False
    assert response.message == "Orders could not be loaded. Please retry."


def test_transport_input_has_no_customer_selector():
    assert [field.name for field in fields(TelegramCustomerOrderListingInput)] == [
        "authenticated_telegram_user_id",
        "page",
        "page_size",
    ]