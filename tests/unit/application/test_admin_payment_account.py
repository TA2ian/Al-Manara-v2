import pytest
from uuid import uuid4

from app.application.admin_payment_account import AdminPaymentAccountService
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    async def create_confirmation(self, *args):
        self.calls.append(("create_confirmation", *args))
        return uuid4()

    async def list(self, *args):
        self.calls.append(("list", *args))
        return []

    async def upsert(self, *args):
        self.calls.append(("upsert", *args))
        return object()

    async def set_active(self, *args):
        self.calls.append(("set_active", *args))
        return object()


@pytest.mark.asyncio
async def test_backup_payment_account_management_requires_emergency_mode() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository, emergency_mode=False)
    session_id = uuid4()
    setup = PaymentMethodSetup("Admin", "0999999999", "0999999999", "telegram-file")

    with pytest.raises(PermissionError):
        await service.request_upsert_confirmation(
            123, "backup", CurrencyCode.USD, setup, session_id
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_primary_payment_account_management_remains_available_without_emergency() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository, emergency_mode=False)
    session_id = uuid4()
    setup = PaymentMethodSetup("Admin", "0999999999", "0999999999", "telegram-file")

    confirmation = await service.request_upsert_confirmation(
        123, "primary", CurrencyCode.USD, setup, session_id
    )

    assert confirmation
    assert repository.calls[0][0] == "create_confirmation"
    assert repository.calls[0][2] == "primary"


@pytest.mark.asyncio
async def test_backup_payment_account_management_is_available_in_emergency() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository, emergency_mode=True)
    session_id = uuid4()
    setup = PaymentMethodSetup("Admin", "0999999999", "0999999999", "telegram-file")

    confirmation = await service.request_upsert_confirmation(
        123, "backup", CurrencyCode.USD, setup, session_id
    )

    assert confirmation
    assert repository.calls[0][2] == "backup"
