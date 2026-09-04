from uuid import UUID

import pytest

from app.application.disable_wallet import DisableWalletResult
from app.application.register_wallet import RegisterWalletResult
from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus
from app.runtime.telegram.wallets import (
    TelegramWalletHandler,
    TelegramWalletInput,
    TelegramWalletRegistrationInput,
    WalletMessages,
)


class Listing:
    def __init__(self, wallets):
        self.wallets = wallets

    async def execute(self, command):
        return tuple(self.wallets)


class Registration:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def execute(self, command):
        if self.error:
            raise self.error
        return self.result


class Disabling:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def execute(self, command):
        if self.error:
            raise self.error
        return self.result


def wallet():
    return Wallet(
        wallet_id=UUID("11111111-1111-1111-1111-111111111111"),
        user_id=7,
        network=NetworkCode.BEP20,
        address="0x1234567890123456789012345678901234567890",
        status=WalletStatus.VERIFIED,
    )


def handler(listing=None, registration=None, disabling=None):
    return TelegramWalletHandler(
        listing or Listing([]),
        registration or Registration(RegisterWalletResult(wallet().wallet_id, "pending")),
        disabling or Disabling(DisableWalletResult(False, False, "")),
    )


@pytest.mark.asyncio
async def test_list_renders_verified_wallets():
    response = await handler(Listing([wallet()])).list(7)
    assert response.ok is True
    assert wallet().address in response.text


@pytest.mark.asyncio
async def test_list_handles_empty_wallets():
    response = await handler().list(7)
    assert response.ok is True
    assert response.text == WalletMessages.EMPTY


@pytest.mark.asyncio
async def test_register_returns_pending_confirmation():
    response = await handler().register(
        TelegramWalletRegistrationInput(7, wallet().address, "BEP20", wallet().address, "file", "Main")
    )
    assert response.ok is True
    assert response.text == WalletMessages.PENDING


@pytest.mark.asyncio
async def test_disable_requires_confirmation():
    disabling = Disabling(DisableWalletResult(False, True, "confirm"))
    response = await handler(disabling=disabling).disable(TelegramWalletInput(7, wallet().wallet_id, False))
    assert response.ok is False
    assert response.text == "confirm"


@pytest.mark.asyncio
async def test_disable_success_hides_internal_details():
    disabling = Disabling(DisableWalletResult(True, False, "wallet disabled"))
    response = await handler(disabling=disabling).disable(TelegramWalletInput(7, wallet().wallet_id, True))
    assert response.ok is True
    assert response.text == WalletMessages.DISABLED
