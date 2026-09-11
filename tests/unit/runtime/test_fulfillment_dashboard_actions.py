from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.admin_order_listing import AdminOrderListItem, AdminOrderPage
from app.runtime.telegram.admin_dashboard import _render_orders


def _page(claimed_by: int | None, version: int = 7) -> AdminOrderPage:
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


def test_fulfillment_list_exposes_claim_when_unclaimed() -> None:
    page = _page(None)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert "الطلبات المعتمدة للتنفيذ" in text
    assert markup is not None
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == [
        f"admin:fulfillment:claim:{page.items[0].internal_order_id}:7",
    ]


def test_fulfillment_list_exposes_complete_only_to_claim_owner() -> None:
    page = _page(1001, version=8)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert markup is not None
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == [
        f"admin:fulfillment:complete:{page.items[0].internal_order_id}:8",
    ]
    assert "مستلم من مدير آخر" not in text


def test_fulfillment_list_does_not_offer_action_to_non_owner() -> None:
    page = _page(2002, version=9)
    text, markup = _render_orders(
        page,
        fulfillment_actions=True,
        current_admin_user_id=1001,
    )

    assert markup is None
    assert "مستلم من مدير آخر" in text
    assert "admin:fulfillment:" not in text
