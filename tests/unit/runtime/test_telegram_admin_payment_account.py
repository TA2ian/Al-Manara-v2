import pytest

from app.runtime.telegram.admin_payment_account import (
    PAYMENT_ACCOUNT_ERROR_MESSAGE,
    TelegramAdminPaymentAccountHandler,
)


class FailingPaymentAccountService:
    async def list(self, _admin_user_id, _actor_type):
        raise ValueError()


@pytest.mark.asyncio
async def test_list_returns_retry_guidance_for_empty_payment_account_error():
    response = await TelegramAdminPaymentAccountHandler(
        FailingPaymentAccountService()  # type: ignore[arg-type]
    ).list(1, "primary")

    assert response.ok is False
    assert response.message == PAYMENT_ACCOUNT_ERROR_MESSAGE