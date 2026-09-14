from uuid import uuid4

import pytest

from app.application.admin_order_closure import AdminOrderClosureResult, MAX_REASON_LENGTH, MIN_REASON_LENGTH
from app.runtime.telegram.admin_order_closure import (
    TelegramAdminClosureInput,
    TelegramAdminOrderClosureHandler,
    parse_closure_callback,
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
async def test_handler_forwards_and_normalizes_free_text_reason() -> None:
    order_id = uuid4()
    session_id = uuid4()
    service = FakeService(AdminOrderClosureResult(order_id, "ORD-CLOSE01", "CLOSED_WITHOUT_FULFILLMENT", 4, False))
    handler = TelegramAdminOrderClosureHandler(service)

    response = await handler.handle(
        TelegramAdminClosureInput(100, order_id, 3, session_id, "  duplicate   payment  ", "close-1")
    )

    assert response.ok is True
    assert response.status == "CLOSED_WITHOUT_FULFILLMENT"
    assert response.version == 4
    assert service.command.internal_order_id == order_id
    assert service.command.session_id == session_id
    assert service.command.reason == "duplicate payment"


@pytest.mark.asyncio
async def test_handler_rejects_empty_or_oversized_reason_before_service() -> None:
    service = FakeService()
    handler = TelegramAdminOrderClosureHandler(service)

    empty = await handler.handle(TelegramAdminClosureInput(100, uuid4(), 3, uuid4(), "  ", "close-2"))
    oversized = await handler.handle(TelegramAdminClosureInput(100, uuid4(), 3, uuid4(), "x" * (MAX_REASON_LENGTH + 1), "close-3"))

    assert empty.ok is False
    assert oversized.ok is False
    assert service.command is None


@pytest.mark.asyncio
async def test_handler_hides_persistence_errors() -> None:
    service = FakeService(error=RuntimeError("stale order version"))
    handler = TelegramAdminOrderClosureHandler(service)

    response = await handler.handle(TelegramAdminClosureInput(100, uuid4(), 3, uuid4(), "valid reason", "close-4"))

    assert response.ok is False
    assert "stale" not in response.message


def test_closure_callback_parser_is_strict() -> None:
    order_id = uuid4()
    valid = f"admin:closure:confirm:{order_id}:12"

    assert parse_closure_callback(valid) == ("confirm", order_id, 12)
    assert parse_closure_callback("admin:closure:confirm:not-a-uuid:12") is None
    assert parse_closure_callback(f"admin:closure:confirm:{order_id}:0") == ("confirm", order_id, 0)
    assert parse_closure_callback(f"admin:closure:confirm:{order_id}:12:extra") is None


def test_reason_contract_is_bounded() -> None:
    assert MIN_REASON_LENGTH == 3
    assert MAX_REASON_LENGTH == 1000
