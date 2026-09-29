from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.create_purchase_order import CreatePurchaseOrderCommand
from app.runtime.telegram.contracts import TelegramOrderInput, TelegramOrderMessages
from app.runtime.telegram.order_creation_handler import TelegramOrderCreationHandler


@dataclass(frozen=True)
class FakeOrder:
    public_order_code: str = "AM-000123"


class FakeOrderService:
    def __init__(self, result=FakeOrder()):
        self.result = result
        self.commands: list[CreatePurchaseOrderCommand] = []

    async def create(self, command: CreatePurchaseOrderCommand):
        self.commands.append(command)
        return self.result


def valid_input() -> TelegramOrderInput:
    return TelegramOrderInput(
        user_id=42,
        wallet_id=uuid4(),
        network_code="TRC20",
        requested_amount=Decimal("100"),
        payment_currency="USDT",
        idempotency_key="tg:42:order:1",
    )


@pytest.mark.asyncio
async def test_handler_maps_valid_input_to_application_command() -> None:
    service = FakeOrderService()
    response = await TelegramOrderCreationHandler(service).handle(valid_input())

    assert response.ok is True
    assert response.order_code == "AM-000123"
    assert response.text == "تم إنشاء الطلب بنجاح: AM-000123"
    assert service.commands[0].user_id == 42
    assert service.commands[0].requested_amount == Decimal("100")


@pytest.mark.asyncio
async def test_handler_hides_internal_configuration_errors() -> None:
    class BrokenService:
        async def create(self, command):
            raise RuntimeError("secret database connection details")

    response = await TelegramOrderCreationHandler(BrokenService()).handle(valid_input())

    assert response.ok is False
    assert response.text == TelegramOrderMessages.CONFIGURATION_ERROR
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_handler_maps_wallet_lookup_failure() -> None:
    class MissingWalletService:
        async def create(self, command):
            raise LookupError("wallet not found")

    response = await TelegramOrderCreationHandler(MissingWalletService()).handle(valid_input())

    assert response.ok is False
    assert response.text == TelegramOrderMessages.WALLET_NOT_AVAILABLE


def test_telegram_order_input_rejects_invalid_amount() -> None:
    with pytest.raises(ValueError):
        TelegramOrderInput.from_values(
            user_id=42,
            wallet_id=str(uuid4()),
            network_code="TRC20",
            requested_amount="nan",
            payment_currency="USDT",
            idempotency_key="tg:42:order:1",
        )
