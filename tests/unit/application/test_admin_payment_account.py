import pytest

from app.application.admin_payment_account import AdminPaymentAccountService
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    async def list(self, admin_telegram_user_id, actor_type):
        self.calls.append(("list", admin_telegram_user_id, actor_type))
        return []

    async def upsert(self, admin_telegram_user_id, actor_type, currency, setup):
        self.calls.append(("upsert", admin_telegram_user_id, actor_type, currency, setup))
        return object()

    async def set_active(self, admin_telegram_user_id, actor_type, currency, is_active):
        self.calls.append(("set_active", admin_telegram_user_id, actor_type, currency, is_active))
        return object()


@pytest.mark.asyncio
async def test_service_normalizes_admin_actor_before_repository_call() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository)

    await service.list(123, " PRIMARY ")

    assert repository.calls == [("list", 123, "primary")]


@pytest.mark.asyncio
async def test_service_rejects_invalid_admin_and_currency() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository)
    setup = PaymentMethodSetup("Admin", "0999999999", "0999999999", "telegram-file")

    with pytest.raises(ValueError):
        await service.upsert(0, "primary", CurrencyCode.USD, setup)
    with pytest.raises(ValueError):
        await service.upsert(123, "primary", "USD", setup)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_service_forwards_valid_setup() -> None:
    repository = FakeRepository()
    service = AdminPaymentAccountService(repository)
    setup = PaymentMethodSetup(" Admin ", "shamcash:0999999999", "0999999999", " telegram-file ")

    await service.upsert(123, "backup", CurrencyCode.NEW_SYP, setup)

    call = repository.calls[0]
    assert call[:4] == ("upsert", 123, "backup", CurrencyCode.NEW_SYP)
    assert call[4] == setup
