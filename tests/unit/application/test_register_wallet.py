from uuid import UUID

import pytest

from app.application.register_wallet import RegisterWalletCommand, RegisterWalletService
from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus


class Wallets:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = None

    async def find_verified_by_address(self, address):
        return self.existing

    async def create_pending(self, **kwargs):
        self.created = kwargs
        return Wallet(
            wallet_id=UUID("22222222-2222-2222-2222-222222222222"),
            user_id=kwargs["user_id"],
            network=NetworkCode(kwargs["network"]),
            address=kwargs["address"],
            status=WalletStatus.PENDING,
        )


def command(**overrides):
    values = dict(
        user_id=7,
        address="0x1234567890123456789012345678901234567890",
        network="BEP20",
        qr_address="ethereum:0x1234567890123456789012345678901234567890",
        qr_image_file_id="telegram-file-id",
        label="Main wallet",
    )
    values.update(overrides)
    return RegisterWalletCommand(**values)


@pytest.mark.asyncio
async def test_registers_wallet_as_pending():
    repo = Wallets()
    result = await RegisterWalletService(repo).execute(command())
    assert result.wallet_id == UUID("22222222-2222-2222-2222-222222222222")
    assert result.status == "pending"
    assert repo.created["network"] == "BEP20"


@pytest.mark.asyncio
async def test_rejects_qr_address_mismatch():
    with pytest.raises(ValueError, match="qr address"):
        await RegisterWalletService(Wallets()).execute(command(qr_address="tron:T123"))


@pytest.mark.asyncio
async def test_rejects_verified_duplicate():
    duplicate = Wallet(
        wallet_id=UUID("33333333-3333-3333-3333-333333333333"),
        user_id=9,
        network=NetworkCode.BEP20,
        address="0x1234567890123456789012345678901234567890",
        status=WalletStatus.VERIFIED,
    )
    with pytest.raises(ValueError, match="already verified"):
        await RegisterWalletService(Wallets(duplicate)).execute(command())
