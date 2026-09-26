from decimal import Decimal

import pytest

from app.domain.money import MoneyError, OrderFinancials


POLICY = "ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001"


def test_service_and_network_fee_are_deducted_from_requested_usdt() -> None:
    financials = OrderFinancials.calculate(
        Decimal("100"), Decimal("10"), Decimal("1.50"), "USD", None, POLICY
    )

    assert financials.requested_amount == Decimal("100.000")
    assert financials.fee_amount == Decimal("10.000")
    assert financials.network_fee_amount == Decimal("1.500")
    assert financials.net_usdt_amount == Decimal("88.500")
    assert financials.local_amount == Decimal("100.00")


def test_syp_local_amount_does_not_include_fees() -> None:
    financials = OrderFinancials.calculate(
        Decimal("100"), Decimal("10"), Decimal("1.50"), "NEW.SYP", Decimal("135"), POLICY
    )

    assert financials.fee_amount == Decimal("10.000")
    assert financials.network_fee_amount == Decimal("1.500")
    assert financials.net_usdt_amount == Decimal("88.500")
    assert financials.local_amount == Decimal("13500.00")


def test_rounding_is_half_up_with_network_fee() -> None:
    financials = OrderFinancials.calculate(
        Decimal("1.005"), Decimal("10"), Decimal("0.001"), "USD", None, POLICY
    )

    assert financials.requested_amount == Decimal("1.005")
    assert financials.fee_amount == Decimal("0.101")
    assert financials.network_fee_amount == Decimal("0.001")
    assert financials.net_usdt_amount == Decimal("0.903")


def test_usd_rejects_exchange_rate() -> None:
    with pytest.raises(MoneyError, match="must not use an exchange rate"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), Decimal("0.15"), "USD", Decimal("135"), POLICY
        )


def test_new_syp_requires_positive_exchange_rate() -> None:
    with pytest.raises(MoneyError, match="requires a positive exchange rate"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), Decimal("0.15"), "NEW.SYP", None, POLICY
        )


def test_network_fee_cannot_reduce_net_amount_to_zero() -> None:
    with pytest.raises(MoneyError, match="net_usdt_amount must remain positive"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), Decimal("9.500"), "USD", None, POLICY
        )


def test_network_fee_must_be_non_negative() -> None:
    with pytest.raises(MoneyError, match="network_fee_amount must be non-negative"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), Decimal("-0.001"), "USD", None, POLICY
        )
