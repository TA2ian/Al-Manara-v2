from uuid import uuid4

import pytest

from app.application.disable_wallet import (
    DISABLE_WALLET_WARNING,
    DisableWalletCommand,
    DisableWalletService,
)
from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus


class FakeWalletRepository:
    def __init__(self, wallet: Wallet | None) -> None:
        self.wallet = wallet
        self.disable_calls = 0
        self.disabled = False

    async def get_for_user(self, wallet_id, user_id):
        if self.wallet is None:
            return None
        if self.wallet.wallet_id != wallet_id or self.wallet.user_id != user_id:
            return None
        if self.disabled:
            return Wallet(
                self.wallet.wallet_id,
                self.wallet.user_id,
                self.wallet.network,
                self.wallet.address,
                WalletStatus.DISABLED,
            )
        return self.wallet

    async def disable_verified_for_user(self, wallet_id, user_id):
        self.disable_calls += 1
        if (
            self.wallet is None
            or self.wallet.wallet_id != wallet_id
            or self.wallet.user_id != user_id
            or self.wallet.status is not WalletStatus.VERIFIED
        ):
            return False
        self.disabled = True
        return True


class FakeAudit:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event, *, actor_user_id, target_id, metadata):
        self.events.append((event, actor_user_id, target_id, dict(metadata)))


def make_wallet(status=WalletStatus.VERIFIED):
    return Wallet(
        uuid4(),
        10,
        NetworkCode.BEP20,
        "0x" + "a" * 40,
        status,
    )


@pytest.mark.asyncio
async def test_disable_requires_explicit_confirmation_without_mutation():
    wallet = make_wallet()
    repo = FakeWalletRepository(wallet)
    audit = FakeAudit()
    service = DisableWalletService(repo, audit)

    result = await service.execute(DisableWalletCommand(wallet.wallet_id, 10))

    assert result.confirmation_required is True
    assert result.disabled is False
    assert result.message == DISABLE_WALLET_WARNING
    assert repo.disable_calls == 0
    assert audit.events == []


@pytest.mark.asyncio
async def test_cancel_is_represented_by_no_confirmation_and_does_not_mutate():
    wallet = make_wallet()
    repo = FakeWalletRepository(wallet)
    audit = FakeAudit()
    service = DisableWalletService(repo, audit)

    result = await service.execute(DisableWalletCommand(wallet.wallet_id, 10, confirmed=False))

    assert result.disabled is False
    assert repo.disable_calls == 0
    assert audit.events == []


@pytest.mark.asyncio
async def test_confirmed_disable_updates_once_and_audits():
    wallet = make_wallet()
    repo = FakeWalletRepository(wallet)
    audit = FakeAudit()
    service = DisableWalletService(repo, audit)

    result = await service.execute(DisableWalletCommand(wallet.wallet_id, 10, confirmed=True))

    assert result.disabled is True
    assert repo.disable_calls == 1
    assert audit.events == [
        (
            "wallet_disabled",
            10,
            wallet.wallet_id,
            {"wallet_status": "disabled"},
        )
    ]


@pytest.mark.asyncio
async def test_unknown_or_other_users_wallet_is_not_mutated():
    wallet = make_wallet()
    repo = FakeWalletRepository(wallet)
    service = DisableWalletService(repo, FakeAudit())

    with pytest.raises(LookupError, match="not found"):
        await service.execute(DisableWalletCommand(wallet.wallet_id, 11, confirmed=True))

    assert repo.disable_calls == 0


@pytest.mark.asyncio
async def test_non_verified_wallet_cannot_be_disabled():
    wallet = make_wallet(WalletStatus.PENDING)
    repo = FakeWalletRepository(wallet)
    service = DisableWalletService(repo, FakeAudit())

    with pytest.raises(ValueError, match="only a verified"):
        await service.execute(DisableWalletCommand(wallet.wallet_id, 10, confirmed=True))

    assert repo.disable_calls == 0


@pytest.mark.asyncio
async def test_already_disabled_wallet_is_idempotent_and_not_audit_written_again():
    wallet = make_wallet()
    repo = FakeWalletRepository(wallet)
    audit = FakeAudit()
    service = DisableWalletService(repo, audit)

    await service.execute(DisableWalletCommand(wallet.wallet_id, 10, confirmed=True))
    result = await service.execute(DisableWalletCommand(wallet.wallet_id, 10, confirmed=True))

    assert result.disabled is False
    assert result.confirmation_required is False
    assert result.message == "wallet is already disabled"
    assert repo.disable_calls == 1
    assert len(audit.events) == 1
