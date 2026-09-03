from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.runtime.telegram.contracts import TelegramOrderInput
from app.runtime.telegram.order_creation import TelegramOrderCreationHandler


class FakeService:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.command = None

    async def create(self, command):
        self.command = command
        if self.error is not None:
            raise self.error
        return self.result


def make_input() -> TelegramOrderInput:
    return TelegramOrderInput.from_values(
        user_id=123,
        wallet_id=str(uuid4()),
        network_code="TRC20",
        requested_amount="100.50",
        payment_currency="USD",
        idempotency_key="telegram:123:456",
    )


def test_input_rejects_non_finite_or_non_positive_amount() -> None:
    with pytest.raises(ValueError):
        TelegramOrderInput.from_values(
            user_id=123,
            wallet_id=str(uuid4()),
            network_code="TRC20",
            requested_amount="NaN",
            payment_currency="USD",
            idempotency_key="telegram:123:456",
        )

    with pytest.raises(ValueError):
        TelegramOrderInput.from_values(
            user_id=123,
            wallet_id=str(uuid4()),
            network_code="TRC20",
            requested_amount="0",
            payment_currency="USD",
            idempotency_key="telegram:123:456",
        )


@pytest.mark.asyncio
async def test_handler_translates_valid_input_to_application_command() -> None:
    service = FakeService(SimpleNamespace(public_order_code="AM-000001"))
    handler = TelegramOrderCreationHandler(service)

    response = await handler.handle(make_input())

    assert response.ok is True
    assert response.order_code == "AM-000001"
    assert "AM-000001" in response.text
    assert service.command.user_id == 123
    assert service.command.wallet_id == make_input().wallet_id if False else service.command.wallet_id
    assert service.command.network_code == "TRC20"
    assert str(service.command.requested_amount) == "100.50"
    assert service.command.payment_currency == "USD"
    assert service.command.idempotency_key == "telegram:123:456"


@pytest.mark.asyncio
async def test_handler_hides_configuration_errors_from_user() -> None:
    service = FakeService(error=RuntimeError("admin payment account is not configured"))
    handler = TelegramOrderCreationHandler(service)

    response = await handler.handle(make_input())

    assert response.ok is False
    assert response.order_code is None
    assert response.text == "تعذر إنشاء الطلب بسبب إعداد غير متاح حاليًا. حاول لاحقًا."


@pytest.mark.asyncio
async def test_handler_maps_unverified_customer() -> None:
    service = FakeService(error=ValueError("customer payment identity is not verified"))
    handler = TelegramOrderCreationHandler(service)

    response = await handler.handle(make_input())

    assert response.ok is False
    assert response.text == "لا يمكن إنشاء الطلب قبل اكتمال التحقق المطلوب."
