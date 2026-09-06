from types import SimpleNamespace
from uuid import UUID

from app.runtime.telegram.admin_dashboard import _render_orders


ORDER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _page(claimed_by=None):
    item = SimpleNamespace(
        internal_order_id=ORDER_ID,
        public_order_code="AM-0001",
        user_telegram_id=123,
        network_code="BEP20",
        status="APPROVED",
        version=8,
        fulfillment_claimed_by=claimed_by,
    )
    return SimpleNamespace(items=(item,), total_count=1, page=0, page_size=5)


def test_unclaimed_fulfillment_order_exposes_claim_action():
    text, markup = _render_orders(
        _page(),
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert "استلم" in markup.inline_keyboard[0][0].text
    assert markup.inline_keyboard[0][0].callback_data == f"admin:fulfillment:claim:{ORDER_ID}:8"
    assert "مدير آخر" not in text


def test_current_admin_claim_exposes_version_bound_complete_action():
    text, markup = _render_orders(
        _page(claimed_by=1001),
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert "إتمام التسليم" == markup.inline_keyboard[0][0].text
    assert markup.inline_keyboard[0][0].callback_data == f"admin:fulfillment:complete:{ORDER_ID}:8"
    assert "مدير آخر" not in text


def test_other_admin_claim_has_no_complete_action():
    text, markup = _render_orders(
        _page(claimed_by=2002),
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert markup is None
    assert "التنفيذ مستلم من مدير آخر" in text
