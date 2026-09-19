import pytest

from app.domain.wallet_registration import (
    WalletRegistration,
    normalize_qr_address,
    normalize_wallet_address,
    validate_wallet_address,
    validate_wallet_text,
)


EVM_ADDRESS = "0x1234567890123456789012345678901234567890"
TRON_ADDRESS = "TA4Y62o6YC2Zsck9rZVGTvqW1AQ7X9zTnj"
SOL_ADDRESS = "So11111111111111111111111111111111111111112"


def test_normalize_qr_address_removes_known_prefixes() -> None:
    assert normalize_qr_address("ethereum:0xabc") == "0xabc"
    assert normalize_qr_address("TRON:T123") == "T123"
    assert normalize_qr_address("ethereum:0xabc@1?value=10") == "0xabc"
    assert normalize_qr_address(f"solana:{SOL_ADDRESS}?amount=1") == SOL_ADDRESS
    assert normalize_qr_address("  T 123  ") == "T 123"


def test_validate_wallet_address_accepts_evm_networks() -> None:
    for network in ("BEP20", "ARB", "ETH", "POLYGON"):
        assert validate_wallet_address(EVM_ADDRESS, network) == EVM_ADDRESS


def test_validate_wallet_address_rejects_invalid_evm_and_cross_network_addresses() -> None:
    with pytest.raises(ValueError, match="invalid BEP20"):
        validate_wallet_address("0x123", "BEP20")
    with pytest.raises(ValueError, match="invalid TRC20"):
        validate_wallet_address(EVM_ADDRESS, "TRC20")
    with pytest.raises(ValueError, match="invalid SOL"):
        validate_wallet_address(EVM_ADDRESS, "SOL")


def test_validate_wallet_address_accepts_valid_tron_checksum() -> None:
    assert validate_wallet_address(TRON_ADDRESS, "TRC20") == TRON_ADDRESS


def test_validate_wallet_address_rejects_invalid_tron_checksum() -> None:
    invalid = TRON_ADDRESS[:-1] + ("1" if TRON_ADDRESS[-1] != "1" else "2")
    with pytest.raises(ValueError, match="invalid TRC20"):
        validate_wallet_address(invalid, "TRC20")


def test_validate_wallet_address_accepts_solana_public_key() -> None:
    assert validate_wallet_address(SOL_ADDRESS, "SOL") == SOL_ADDRESS


def test_validate_wallet_address_rejects_invalid_solana_length_or_charset() -> None:
    with pytest.raises(ValueError, match="invalid SOL"):
        validate_wallet_address("0", "SOL")
    with pytest.raises(ValueError, match="invalid SOL"):
        validate_wallet_address("0OIl" + "1" * 28, "SOL")


def test_normalize_wallet_address_only_strips_outer_whitespace() -> None:
    assert normalize_wallet_address("  0xabc  ") == "0xabc"


def test_validate_wallet_text_requires_real_address_and_supported_network() -> None:
    assert validate_wallet_text(EVM_ADDRESS, "bep20", " Main Wallet ") == (
        EVM_ADDRESS,
        "BEP20",
        "Main Wallet",
    )
    with pytest.raises(ValueError, match="unsupported"):
        validate_wallet_text("addr", "TON", "Main")


def test_wallet_registration_requires_valid_qr_match_and_file_id() -> None:
    wallet = WalletRegistration(EVM_ADDRESS, "ETH", f"ethereum:{EVM_ADDRESS}", "telegram-file", "Main")
    assert wallet.address == EVM_ADDRESS

    with pytest.raises(ValueError, match="does not match"):
        WalletRegistration(EVM_ADDRESS, "ETH", "0x9999999999999999999999999999999999999999", "telegram-file", "Main")

    with pytest.raises(ValueError, match="qr image file id"):
        WalletRegistration(EVM_ADDRESS, "ETH", EVM_ADDRESS, "", "Main")


def test_wallet_registration_supports_all_six_networks() -> None:
    cases = (
        ("BEP20", EVM_ADDRESS, EVM_ADDRESS),
        ("TRC20", TRON_ADDRESS, f"TRON:{TRON_ADDRESS}"),
        ("ARB", EVM_ADDRESS, EVM_ADDRESS),
        ("ETH", EVM_ADDRESS, EVM_ADDRESS),
        ("SOL", SOL_ADDRESS, f"solana:{SOL_ADDRESS}"),
        ("POLYGON", EVM_ADDRESS, EVM_ADDRESS),
    )
    for network, address, qr in cases:
        registration = WalletRegistration(address, network, qr, "file", "Main")
        assert registration.network == network


def test_wallet_registration_rejects_unsupported_network_and_empty_label() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        WalletRegistration("addr", "TON", "addr", "file", "Main")
    with pytest.raises(ValueError, match="label"):
        WalletRegistration(EVM_ADDRESS, "BEP20", EVM_ADDRESS, "file", "Main")
