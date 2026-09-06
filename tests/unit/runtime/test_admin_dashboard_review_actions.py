from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.admin_order_listing import AdminOrderListItem, AdminOrderPage
from app.runtime.telegram.admin_dashboard import _render_orders


def test_review_order_list_exposes_version_bound_actions() -> None:
    order_id = uuid4()
    page = AdminOrderPage(
        items=(
            AdminOrderListItem(
                internal_order_id=order_id,
                public_order_code="AM-001",
                user_telegram_id=100,
                wallet_id=uuid4(),
                network_code="BEP20",
                status="UNDER_REVIEW",
                version=4,
                requested_amount=Decimal("10"),
                payment_currency="USD",
                local_amount=Decimal("10"),
                created_at=datetime.now(timezone.utc),
            ),
        ),
        page=0,
        page_size=5,
        total_count=1,
    )

    text, markup = _render_orders(page, review_actions=True)

    assert "🔎 طلبات قيد المراجعة" in text
    assert markup is not None
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert callbacks == [
        f"admin:order:approve:{order_id}:4",
        f"admin:order:reject:{order_id}:4",
        f"admin:order:clarify:{order_id}:4",
    ]
