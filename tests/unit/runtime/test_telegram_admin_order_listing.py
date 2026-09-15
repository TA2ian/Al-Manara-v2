from uuid import uuid4

import pytest

from app.application.admin_order_listing import AdminOrderPage
from app.runtime.telegram.admin_order_listing import TelegramAdminOrderListingHandler, TelegramAdminOrderListingInput


class FakeService:
    async def list(self, command):
        self.command = command
        return AdminOrderPage((), command.page, command.page_size, 0)


@pytest.mark.asyncio
async def test_listing_handler_forwards_request():
    service = FakeService()
    response = await TelegramAdminOrderListingHandler(service).handle(
        TelegramAdminOrderListingInput(100, "primary", "review", 1, 10)
    )
    assert response.ok is True
    assert response.page is not None
    assert service.command.actor_type == "primary"
    assert service.command.page == 1


@pytest.mark.asyncio
async def test_listing_handler_rejects_invalid_type_before_service():
    service = FakeService()
    response = await TelegramAdminOrderListingHandler(service).handle(
        TelegramAdminOrderListingInput(100, "primary", "unknown")
    )
    assert response.ok is False
