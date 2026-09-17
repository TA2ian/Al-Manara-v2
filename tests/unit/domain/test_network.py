from decimal import Decimal

from app.domain.network import NetworkCode, get_network, normalize_network


def test_supported_networks_include_exact_six_operational_codes() -> None:
    assert tuple(network.value for network in __import__("app.domain.network", fromlist=["NETWORKS"]).NETWORKS) == (
        "BEP20", "TRC20", "ARB", "ETH", "SOL", "POLYGON"
    )


def test_bep20_network_fee_is_snapshotted_from_configuration() -> None:
    network = get_network(NetworkCode.BEP20)
    assert network.network_fee_amount == Decimal("0.15")
    assert network.min_amount == Decimal("1")
    assert network.max_amount == Decimal("100000")


def test_solana_alias_normalizes_to_sol() -> None:
    assert normalize_network("SOLANA") is NetworkCode.SOL


def test_polygon_alias_normalizes_to_polygon() -> None:
    assert normalize_network("MATIC") is NetworkCode.POLYGON
