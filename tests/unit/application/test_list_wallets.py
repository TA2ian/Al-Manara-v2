from uuid import UUID

import pytest

from app.application.list_wallets import ListWalletsCommand, ListWalletsService
from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus


class Wallets:
    def __init__(self, wallets):
        self.wallets = wallets
        self.user_ids = []

    async def list_verified_for_user(self, user_id):
        self.user_ids.append(user_id)
        return tuple(self.wallets)


def wallet(status=WalletStatus.VERIFIED):
    return Wallet(
        wallet_id=UUID("11111111-1111-1111-1111-111111111111"),
        user_id=7,
        network=NetworkCode.BEP20,
        address="0x1234567890123456789012345678901234567890",
        status=status,
    )


@pytest.mark.asyncio
async def test_lists_verified_wallets():
    repo = Wallets([wallet(), wallet(WalletStatus.DISABLED)])
    result = await ListWalletsService(repo).execute(ListWalletsCommand(7))
    assert result == (wallet(),)
    assert repo.user_ids == [7]


@pytest.mark.asyncio
async def test_rejects_invalid_user_id():
    with pytest.raises(ValueError, match="invalid customer id"):
        await ListWalletsService(Wallets([])).execute(ListWalletsCommand(0))
