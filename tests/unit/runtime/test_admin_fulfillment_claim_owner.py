from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.admin_order_listing import AdminOrderListItem, AdminOrderPage
from app.runtime.telegram.admin_dashboard import _render_orders


def _page(*, claim_owner: int | None) -> AdminOrderPage:
    return AdminOrderPage(
        items=(
            AdminOrderListItem(
                internal_order_id=uuid4(),
                public_order_code="ORD-1",
                user_telegram_id=100,
                wallet_id=uuid4(),
                network_code="BEP20",
                status="APPROVED",
                version=7,
                requested_amount=Decimal("10"),
                payment_currency="USD",
                local_amount=Decimal("10"),
                created_at=datetime.now(timezone.utc),
                fulfillment_claimed_by=claim_owner,
            ),
        ),
        page=0,
        page_size=5,
        total_count=1,
    )


def _callbacks(markup):
    if markup is None:
        return []
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_unclaimed_fulfillment_order_exposes_claim_action():
    page = _page(claim_owner=None)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=200,
    )

    assert "استلام للتنفيذ" in markup.inline_keyboard[0][0].text
    assert _callbacks(markup) == [
        f"admin:fulfillment:claim:{page.items[0].internal_order_id}:7"
    ]
    assert "مدير آخر" not in text


def test_owned_fulfillment_order_exposes_complete_action_with_current_version():
    page = _page(claim_owner=200)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=200,
    )

    assert "إتمام التسليم" in markup.inline_keyboard[0][0].text
    assert _callbacks(markup) == [
        f"admin:fulfillment:complete:{page.items[0].internal_order_id}:7"
    ]
    assert "مدير آخر" not in text


def test_foreign_fulfillment_claim_exposes_no_completion_action():
    page = _page(claim_owner=300)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=200,
    )

    assert markup is None
    assert "التنفيذ مستلم من مدير آخر" in text
    assert "إتمام التسليم" not in text
