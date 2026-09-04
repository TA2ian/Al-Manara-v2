from uuid import UUID

import pytest

from app.application.disable_wallet import DisableWalletResult
from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus
from app.runtime.telegram.wallets import TelegramWalletHandler, TelegramWalletInput, WalletMessages


class Listing:
    def __init__(self, wallets):
        self.wallets = wallets

    async def execute(self, command):
        return tuple(self.wallets)


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


@pytest.mark.asyncio
async def test_list_renders_verified_wallets():
    response = await TelegramWalletHandler(Listing([wallet()]), Disabling()).list(7)
    assert response.ok is True
    assert wallet().address in response.text


@pytest.mark.asyncio
async def test_list_handles_empty_wallets():
    response = await TelegramWalletHandler(Listing([]), Disabling()).list(7)
    assert response.ok is True
    assert response.text == WalletMessages.EMPTY


@pytest.mark.asyncio
async def test_disable_requires_confirmation():
    disabling = Disabling(DisableWalletResult(False, True, "confirm"))
    response = await TelegramWalletHandler(Listing([]), disabling).disable(
        TelegramWalletInput(7, wallet().wallet_id, False)
    )
    assert response.ok is False
    assert response.text == "confirm"


@pytest.mark.asyncio
async def test_disable_success_hides_internal_details():
    disabling = Disabling(DisableWalletResult(True, False, "wallet disabled"))
    response = await TelegramWalletHandler(Listing([]), disabling).disable(
        TelegramWalletInput(7, wallet().wallet_id, True)
    )
    assert response.ok is True
    assert response.text == WalletMessages.DISABLED
