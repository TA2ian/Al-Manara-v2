from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.runtime.telegram.customer.purchase_order import _quote_fingerprint, render_confirmation


def make_quote(rate: str | None = None):
    financials = SimpleNamespace(
        requested_amount=Decimal("100.000"),
        fee_amount=Decimal("2.000"),
        fee_percent=Decimal("2"),
        net_usdt_amount=Decimal("98.000"),
        payment_currency="USD" if rate is None else "NEW.SYP",
        local_amount=Decimal("98.00") if rate is None else Decimal("125000.00"),
        exchange_rate=None if rate is None else Decimal(rate),
        rounding_policy_version="rounding-v1",
    )
    snapshot = None if rate is None else SimpleNamespace(version="rate-v1", rate=Decimal(rate))
    return SimpleNamespace(
        financials=financials,
        exchange_rate_snapshot=snapshot,
        fee_policy_snapshot=SimpleNamespace(version="fee-v1"),
    )


def test_render_confirmation_exposes_financial_quote() -> None:
    text = render_confirmation({}, make_quote())
    assert "100.000 USDT" in text
    assert "2.000 USDT (2%)" in text
    assert "98.000 USDT" in text
    assert "98.00 USD" in text
    assert "عرض السعر صالح لمدة 10 دقائق" in text


def test_render_confirmation_includes_exchange_rate_for_new_syp() -> None:
    text = render_confirmation({}, make_quote("1250"))
    assert "125000.00 NEW.SYP" in text
    assert "سعر الصرف: 1250" in text


def test_quote_fingerprint_changes_when_rate_changes() -> None:
    assert _quote_fingerprint(make_quote("1250")) != _quote_fingerprint(make_quote("1300"))
    assert _quote_fingerprint(make_quote()) == _quote_fingerprint(make_quote())
