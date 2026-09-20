from uuid import uuid4

import pytest

from app.application.admin_payment_account import AdminPaymentAccountService
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup
from app.runtime.telegram.admin_payment_account import (
    PAYMENT_ACCOUNT_ERROR_MESSAGE,
    TelegramAdminPaymentAccountHandler,
)


class FailingPaymentAccountService:
    async def list(self, _admin_user_id, _actor_type, _session_id):
        raise ValueError()


class RecordingPaymentAccountRepository:
    def __init__(self) -> None:
        self.confirmation_args = None
        self.upsert_args = None

    async def create_confirmation(self, *args):
        self.confirmation_args = args
        return uuid4()

    async def list(self, *_args):
        return []

    async def upsert(self, *args):
        self.upsert_args = args
        raise AssertionError("upsert should only run from explicit confirmation")

    async def set_active(self, *_args):
        raise AssertionError("set_active should only run from explicit confirmation")


@pytest.mark.asyncio
async def test_list_returns_retry_guidance_for_empty_payment_account_error():
    response = await TelegramAdminPaymentAccountHandler(
        FailingPaymentAccountService()  # type: ignore[arg-type]
    ).list(1, "primary", uuid4())

    assert response.ok is False
    assert response.message == PAYMENT_ACCOUNT_ERROR_MESSAGE


@pytest.mark.asyncio
async def test_request_upsert_confirmation_creates_server_bound_confirmation():
    repository = RecordingPaymentAccountRepository()
    service = AdminPaymentAccountService(repository)
    setup = PaymentMethodSetup(
        recipient_name="Al Manara",
        receiving_address="123456789",
        qr_address="123456789",
        qr_image_file_id="telegram-file-id",
    )
    session_id = uuid4()

    response = await TelegramAdminPaymentAccountHandler(service).request_upsert_confirmation(
        10,
        "primary",
        CurrencyCode.USD,
        setup,
        session_id,
    )

    assert response.ok is True
    assert response.confirmation_id is not None
    assert repository.confirmation_args is not None
    assert repository.confirmation_args[0:4] == (
        10,
        "primary",
        session_id,
        AdminPaymentAccountService.UPSERT_OPERATION,
    )
    assert isinstance(repository.confirmation_args[4], str)
    assert len(repository.confirmation_args[4]) == 64
