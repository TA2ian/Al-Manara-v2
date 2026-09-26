from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.customer_identity import CustomerIdentitySubmission
from app.runtime.telegram.admin_customer_identity import TelegramAdminCustomerIdentityHandler


class FakeService:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def list_pending(self, *args):
        self.calls.append(("list", args))
        if self.error:
            raise self.error
        return (
            CustomerIdentitySubmission(
                uuid4(), 44, "Customer Name", "SC-1", "photo-id", datetime.now(timezone.utc)
            ),
        )

    async def approve(self, *args):
        self.calls.append(("approve", args))
        if self.error:
            raise self.error

    async def reject(self, *args):
        self.calls.append(("reject", args))
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_handler_uses_primary_role_without_accepting_role_input():
    service = FakeService()
    handler = TelegramAdminCustomerIdentityHandler(service)

    response = await handler.list_pending(123)

    assert response.ok
    assert service.calls[0] == ("list", (123, "primary"))


@pytest.mark.asyncio
async def test_handler_returns_safe_nonempty_authorization_failure():
    handler = TelegramAdminCustomerIdentityHandler(FakeService(error=PermissionError("database detail")))

    response = await handler.approve(123, uuid4())

    assert not response.ok
    assert response.message == "غير مصرح لك بمراجعة طلبات التحقق."
    assert "database detail" not in response.message


@pytest.mark.asyncio
async def test_handler_rejects_invalid_reason_without_calling_service():
    service = FakeService()
    handler = TelegramAdminCustomerIdentityHandler(service)

    response = await handler.reject(123, uuid4(), " ")

    assert not response.ok
    assert response.message
    assert service.calls == []