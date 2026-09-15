from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.admin_order_listing import AdminOrderListItem, AdminOrderPage
from app.runtime.telegram.admin_dashboard import _render_orders


def _page(claimed_by: int | None = None, version: int = 5) -> AdminOrderPage:
    return AdminOrderPage(
        items=(
            AdminOrderListItem(
                internal_order_id=uuid4(),
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
                fulfillment_claimed_by=claimed_by,
            ),
        ),
        page=0,
        page_size=5,
        total_count=1,
    )


def _callbacks(markup) -> list[str]:
    if markup is None:
        return []
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_unclaimed_fulfillment_order_exposes_claim_action() -> None:
    page = _page()
    order_id = page.items[0].internal_order_id

    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=700,
    )

    assert "🚚 الطلبات المعتمدة للتنفيذ" in text
    assert _callbacks(markup) == [f"admin:fulfillment:claim:{order_id}:5"]


def test_fulfillment_order_claimed_by_current_admin_exposes_complete_action() -> None:
    page = _page(claimed_by=700, version=6)
    order_id = page.items[0].internal_order_id

    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=700,
    )

    assert "🚚 الطلبات المعتمدة للتنفيذ" in text
    assert _callbacks(markup) == [f"admin:fulfillment:complete:{order_id}:6"]


def test_fulfillment_order_claimed_by_another_admin_exposes_no_action() -> None:
    page = _page(claimed_by=701, version=6)

    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=700,
    )

    assert "التنفيذ مستلم من مدير آخر" in text
    assert markup is None
