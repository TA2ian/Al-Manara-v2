from uuid import uuid4

import pytest

from app.application.admin_order_closure import AdminOrderClosureResult
from app.runtime.telegram.admin_order_closure import (
    TelegramAdminClosureInput,
    TelegramAdminOrderClosureHandler,
)


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.command = None

    async def close_without_fulfillment(self, command):
        self.command = command
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_handler_forwards_privileged_closure_request() -> None:
    order_id = uuid4()
    session_id = uuid4()
    service = FakeService(
        AdminOrderClosureResult(order_id, "ORD-CLOSE01", "CLOSED_WITHOUT_FULFILLMENT", 4, False)
    )
    handler = TelegramAdminOrderClosureHandler(service)

    response = await handler.handle(
        TelegramAdminClosureInput(100, order_id, 3, session_id, "reason", "close-1")
    )

    assert response.ok is True
    assert response.status == "CLOSED_WITHOUT_FULFILLMENT"
    assert response.version == 4
    assert service.command.internal_order_id == order_id
    assert service.command.session_id == session_id


@pytest.mark.asyncio
async def test_handler_hides_persistence_errors() -> None:
    service = FakeService(error=RuntimeError("stale order version"))
    handler = TelegramAdminOrderClosureHandler(service)

    response = await handler.handle(
        TelegramAdminClosureInput(100, uuid4(), 3, uuid4(), "reason", "close-2")
    )

    assert response.ok is False
    assert "stale" not in response.message
