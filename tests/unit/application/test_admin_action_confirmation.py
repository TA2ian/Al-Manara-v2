from uuid import uuid4

import pytest

from app.application.admin_action_confirmation import AdminActionConfirmationService


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, *args):
        self.calls.append(args)
        return args[2]


@pytest.mark.asyncio
async def test_create_normalizes_valid_confirmation_request_without_mutating_fingerprint() -> None:
    repository = FakeRepository()
    service = AdminActionConfirmationService(repository)
    session_id = uuid4()

    result = await service.create(
        100,
        "primary",
        session_id,
        "order.reopen_receipt",
        "a" * 64,
    )

    assert result == session_id
    assert repository.calls == [(100, "primary", session_id, "order.reopen_receipt", "a" * 64)]


@pytest.mark.asyncio
async def test_create_rejects_unsupported_operation_before_persistence() -> None:
    repository = FakeRepository()
    service = AdminActionConfirmationService(repository)

    with pytest.raises(ValueError, match="unsupported confirmation operation"):
        await service.create(100, "primary", uuid4(), "order.approve", "a" * 64)

    assert repository.calls == []


@pytest.mark.asyncio
async def test_create_rejects_non_hex_fingerprint_before_persistence() -> None:
    repository = FakeRepository()
    service = AdminActionConfirmationService(repository)

    with pytest.raises(ValueError, match="fingerprint"):
        await service.create(100, "primary", uuid4(), "fulfillment.complete", "g" * 64)

    assert repository.calls == []


@pytest.mark.asyncio
async def test_create_rejects_uppercase_fingerprint_before_persistence() -> None:
    repository = FakeRepository()
    service = AdminActionConfirmationService(repository)

    with pytest.raises(ValueError, match="fingerprint"):
        await service.create(100, "primary", uuid4(), "fulfillment.complete", "A" * 64)

    assert repository.calls == []
