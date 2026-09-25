from uuid import uuid4

import pytest

from app.runtime.telegram.admin_order_reopen import TelegramAdminOrderRecoveryHandler


class FakeResolver:
    async def resolve_actor_type(self, user_id: int):
        return "primary"


class FakeService:
    def __init__(self):
        self.commands = []

    async def reopen_for_receipt(self, command):
        self.commands.append(command)
        class Result:
            version = 4
        return Result()


class FakeConfirmation:
    async def create(self, *args):
        return uuid4()


@pytest.mark.asyncio
async def test_fingerprint_is_stable_for_same_operation() -> None:
    order_id = uuid4()
    first = TelegramAdminOrderRecoveryHandler.fingerprint(order_id, 2, 100, "primary", "same reason")
    second = TelegramAdminOrderRecoveryHandler.fingerprint(order_id, 2, 100, "primary", "same reason")
    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_handler_requires_service_contract() -> None:
    handler = TelegramAdminOrderRecoveryHandler(FakeService(), FakeResolver(), FakeConfirmation())
    response = await handler.handle(
        admin_user_id=100,
        actor_type="primary",
        order_id=uuid4(),
        expected_version=2,
        session_id=uuid4(),
        confirmation_id=uuid4(),
        request_fingerprint="a" * 64,
        reason="valid reason",
    )
    assert response.ok is True
    assert response.version == 4
