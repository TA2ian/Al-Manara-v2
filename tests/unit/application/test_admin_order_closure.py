from uuid import uuid4

import pytest

from app.application.admin_order_closure import (
    AdminOrderClosureCommand,
    AdminOrderClosureResult,
    AdminOrderClosureService,
)


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    async def close_without_fulfillment(self, *args):
        self.calls.append(args)
        return AdminOrderClosureResult(args[0], "ORD-CLOSE01", "CLOSED_WITHOUT_FULFILLMENT", 4, False)


@pytest.mark.asyncio
async def test_closure_normalizes_reason_and_idempotency_key() -> None:
    repository = FakeRepository()
    service = AdminOrderClosureService(repository)
    order_id = uuid4()
    session_id = uuid4()

    result = await service.close_without_fulfillment(
        AdminOrderClosureCommand(
            internal_order_id=order_id,
            admin_telegram_user_id=100,
            expected_version=3,
            session_id=session_id,
            reason="  no   fulfillment  ",
            idempotency_key="  close-1  ",
        )
    )

    assert result.status == "CLOSED_WITHOUT_FULFILLMENT"
    assert repository.calls == [
        (order_id, 3, 100, session_id, "no fulfillment", "close-1")
    ]


@pytest.mark.asyncio
async def test_invalid_reason_is_rejected_before_persistence() -> None:
    repository = FakeRepository()
    service = AdminOrderClosureService(repository)

    with pytest.raises(ValueError, match="closure reason"):
        await service.close_without_fulfillment(
            AdminOrderClosureCommand(
                uuid4(), 100, 2, uuid4(), "no", "close-2"
            )
        )

    assert repository.calls == []
