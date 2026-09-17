from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.network import NetworkCode, get_network, validate_amount, validate_network_address
from app.domain.wallet import Wallet, WalletStatus


def test_six_supported_networks_are_enabled() -> None:
    for code in (
        NetworkCode.BEP20,
        NetworkCode.TRC20,
        NetworkCode.ARB,
        NetworkCode.ETH,
        NetworkCode.SOL,
        NetworkCode.POLYGON,
    ):
        assert get_network(code).enabled is True


def test_bep20_address_format() -> None:
    network = get_network(NetworkCode.BEP20)
    assert validate_network_address(network, "0x" + "a" * 40) == "0x" + "a" * 40
    with pytest.raises(ValueError):
        validate_network_address(network, "0x" + "a" * 39)


def test_trc20_address_format() -> None:
    network = get_network(NetworkCode.TRC20)
    address = "T" + "a" * 33
    assert validate_network_address(network, address) == address
    with pytest.raises(ValueError):
        validate_network_address(network, "0x" + "a" * 40)


def test_polygon_uses_evm_address_validation() -> None:
    network = get_network(NetworkCode.POLYGON)
    address = "0x" + "a" * 40
    assert validate_network_address(network, address) == address


def test_sol_uses_strict_base58_like_address_validation() -> None:
    network = get_network(NetworkCode.SOL)
    address = "1" * 32
    assert validate_network_address(network, address) == address
    with pytest.raises(ValueError):
        validate_network_address(network, "0x" + "a" * 40)


def test_network_amount_limits_are_domain_rules() -> None:
    network = get_network(NetworkCode.BEP20)
    assert validate_amount(network, Decimal("1")) == Decimal("1")
    assert validate_amount(network, Decimal("100000")) == Decimal("100000")
    with pytest.raises(ValueError):
        validate_amount(network, Decimal("0.999"))
    with pytest.raises(ValueError):
        validate_amount(network, Decimal("100000.001"))


def test_wallet_is_usable_only_when_verified_and_owned() -> None:
    user_id = 42
    wallet = Wallet(uuid4(), user_id, NetworkCode.BEP20, "0x" + "a" * 40, WalletStatus.VERIFIED)

    assert wallet.belongs_to(user_id)
    assert wallet.is_usable_for_order()
    assert not wallet.belongs_to(43)
