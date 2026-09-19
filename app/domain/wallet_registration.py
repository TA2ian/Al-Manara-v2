from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit
from dataclasses import dataclass


SUPPORTED_WALLET_NETWORKS = frozenset({"BEP20", "TRC20", "ARB", "ETH", "SOL", "POLYGON"})
MAX_LABEL_LENGTH = 64
_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {char: index for index, char in enumerate(_BASE58_ALPHABET)}


@dataclass(frozen=True, slots=True)
class WalletRegistration:
    """Validated customer wallet registration payload."""

    address: str
    network: str
    qr_address: str
    qr_image_file_id: str
    label: str

    def __post_init__(self) -> None:
        address = normalize_wallet_address(self.address)
        network = self.network.strip().upper()
        qr_address = normalize_qr_address(self.qr_address)
        file_id = self.qr_image_file_id.strip()
        label = self.label.strip()

        if network not in SUPPORTED_WALLET_NETWORKS:
            raise ValueError("unsupported wallet network")
        address = validate_wallet_address(address, network)
        qr_address = validate_wallet_address(qr_address, network)
        if address.casefold() != qr_address.casefold():
            raise ValueError("qr address does not match wallet address")
        if not file_id:
            raise ValueError("qr image file id is required")
        if not label or len(label) > MAX_LABEL_LENGTH:
            raise ValueError("wallet label is invalid")

        object.__setattr__(self, "address", address)
        object.__setattr__(self, "network", network)
        object.__setattr__(self, "qr_address", qr_address)
        object.__setattr__(self, "qr_image_file_id", file_id)
        object.__setattr__(self, "label", label)


def normalize_wallet_address(value: str) -> str:
    """Canonicalize wallet text without changing address characters."""
    return (value or "").strip()


def normalize_qr_address(value: str) -> str:
    """Extract only the wallet address from supported QR URI payloads."""
    normalized = normalize_wallet_address(value)
    lowered = normalized.casefold()
    prefixes = ("ethereum:", "tron:", "trc20:", "bep20:", "arb:", "eth:", "solana:", "sol:", "polygon:", "usdt:")
    if not any(lowered.startswith(prefix) for prefix in prefixes):
        return normalized.split("?", 1)[0].strip()

    scheme, _, remainder = normalized.partition(":")
    if not remainder:
        return ""
    address = remainder.split("?", 1)[0].strip()
    if scheme.casefold() == "ethereum":
        address = address.split("@", 1)[0].strip()
    return address


def validate_wallet_address(address: str, network: str) -> str:
    """Validate an address offline using network-specific syntax/checksum rules."""
    normalized_network = (network or "").strip().upper()
    normalized_address = normalize_wallet_address(address)
    if normalized_network not in SUPPORTED_WALLET_NETWORKS:
        raise ValueError("unsupported wallet network")
    if not normalized_address:
        raise ValueError("wallet address is required")

    if normalized_network in {"BEP20", "ARB", "ETH", "POLYGON"}:
        if not _EVM_RE.fullmatch(normalized_address):
            raise ValueError(f"invalid {normalized_network} address")
        return normalized_address

    if normalized_network == "TRC20":
        if not _is_tron_base58check_address(normalized_address):
            raise ValueError("invalid TRC20 address")
        return normalized_address

    if normalized_network == "SOL":
        if not _is_solana_public_key(normalized_address):
            raise ValueError("invalid SOL address")
        return normalized_address

    raise ValueError("unsupported wallet network")


def _base58_decode(value: str) -> bytes | None:
    if not value:
        return None
    number = 0
    for char in value:
        digit = _BASE58_INDEX.get(char)
        if digit is None:
            return None
        number = number * 58 + digit

    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return b"\\x00" * leading_zeroes + decoded


def _is_tron_base58check_address(address: str) -> bool:
    decoded = _base58_decode(address)
    if decoded is None or len(decoded) != 25:
        return False
    payload, checksum = decoded[:21], decoded[21:]
    if payload[0] != 0x41:
        return False
    expected = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return checksum == expected


def _is_solana_public_key(address: str) -> bool:
    decoded = _base58_decode(address)
    return decoded is not None and len(decoded) == 32


def validate_wallet_text(address: str, network: str, label: str) -> tuple[str, str, str]:
    normalized_network = (network or "").strip().upper()
    normalized_address = validate_wallet_address(address, normalized_network)
    normalized_label = (label or "").strip()
    if not normalized_label or len(normalized_label) > MAX_LABEL_LENGTH:
        raise ValueError("wallet label is invalid")
    return normalized_address, normalized_network, normalized_label
