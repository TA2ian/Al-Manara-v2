from uuid import uuid4

import pytest

from app.application.admin_order_recovery import (
    AdminOrderRecoveryCommand,
    AdminOrderRecoveryResult,
    AdminOrderRecoveryService,
)


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    async def reopen_for_receipt(self, *args):
        self.calls.append(args)
        return AdminOrderRecoveryResult(args[0], "ORD-REC01", "PENDING_PAYMENT", 8, False)


@pytest.mark.asyncio
async def test_reopen_normalizes_reason_and_fingerprint() -> None:
    repository = FakeRepository()
    service = AdminOrderRecoveryService(repository)
    order_id = uuid4()
    session_id = uuid4()
    confirmation_id = uuid4()

    result = await service.reopen_for_receipt(
        AdminOrderRecoveryCommand(
            order_id,
            100,
            "primary",
            7,
            session_id,
            confirmation_id,
            "a" * 64,
            "  user   supplied   clarification  ",
            "recover-1",
        )
    )

    assert result.status == "PENDING_PAYMENT"
    assert repository.calls == [
        (
            order_id,
            7,
            100,
            "primary",
            session_id,
            confirmation_id,
            "a" * 64,
            "user supplied clarification",
            "recover-1",
        )
    ]


@pytest.mark.asyncio
async def test_reopen_rejects_invalid_fingerprint_before_persistence() -> None:
    repository = FakeRepository()
    service = AdminOrderRecoveryService(repository)

    with pytest.raises(ValueError, match="fingerprint"):
        await service.reopen_for_receipt(
            AdminOrderRecoveryCommand(
                uuid4(), 100, "primary", 1, uuid4(), uuid4(), "not-a-fingerprint", "valid reason", "key"
            )
        )
    assert repository.calls == []
