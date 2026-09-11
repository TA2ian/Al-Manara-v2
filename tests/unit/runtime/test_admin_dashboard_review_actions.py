from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.admin_order_listing import AdminOrderListItem, AdminOrderPage
from app.runtime.telegram.admin_dashboard import _render_orders


def _page(item: AdminOrderListItem) -> AdminOrderPage:
    return AdminOrderPage(
        items=(item,),
        page=0,
        page_size=5,
        total_count=1,
    )


def _item(*, order_id=None, version=4, fulfillment_claimed_by=None) -> AdminOrderListItem:
    return AdminOrderListItem(
        internal_order_id=order_id or uuid4(),
        public_order_code="AM-001",
        user_telegram_id=100,
        wallet_id=uuid4(),
        network_code="BEP20",
        status="APPROVED",
        version=version,
        requested_amount=Decimal("10"),
        payment_currency="USD",
        local_amount=Decimal("10"),
        created_at=datetime.now(timezone.utc),
        fulfillment_claimed_by=fulfillment_claimed_by,
    )


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


def test_review_order_list_exposes_version_bound_actions() -> None:
    order_id = uuid4()
    page = _page(_item(order_id=order_id, version=4, fulfillment_claimed_by=None))
    text, markup = _render_orders(page, review_actions=True)

    assert "🔎 طلبات قيد المراجعة" in text
    assert markup is not None
    assert _callbacks(markup) == [
        f"admin:order:approve:{order_id}:4",
        f"admin:order:reject:{order_id}:4",
        f"admin:order:clarify:{order_id}:4",
    ]


def test_fulfillment_list_exposes_claim_when_order_is_unclaimed() -> None:
    order_id = uuid4()
    text, markup = _render_orders(
        _page(_item(order_id=order_id, version=4)),
        fulfillment_actions=True,
        current_admin_user_id=111,
    )

    assert "🚚 الطلبات المعتمدة للتنفيذ" in text
    assert markup is not None
    assert _callbacks(markup) == [
        f"admin:fulfillment:claim:{order_id}:4",
    ]


def test_fulfillment_list_exposes_complete_only_to_claim_owner() -> None:
    order_id = uuid4()
    text, markup = _render_orders(
        _page(_item(order_id=order_id, version=5, fulfillment_claimed_by=111)),
        fulfillment_actions=True,
        current_admin_user_id=111,
    )

    assert "🚚 الطلبات المعتمدة للتنفيذ" in text
    assert markup is not None
    assert _callbacks(markup) == [
        f"admin:fulfillment:complete:{order_id}:5",
    ]


def test_fulfillment_list_hides_complete_from_non_owner() -> None:
    order_id = uuid4()
    text, markup = _render_orders(
        _page(_item(order_id=order_id, version=5, fulfillment_claimed_by=222)),
        fulfillment_actions=True,
        current_admin_user_id=111,
    )

    assert "التنفيذ مستلم من مدير آخر" in text
    assert markup is None


def test_fulfillment_list_does_not_advertise_complete_without_current_admin_identity() -> None:
    order_id = uuid4()
    text, markup = _render_orders(
        _page(_item(order_id=order_id, version=5, fulfillment_claimed_by=111)),
        fulfillment_actions=True,
        current_admin_user_id=None,
    )

    assert "التنفيذ مستلم من مدير آخر" in text
    assert markup is None
