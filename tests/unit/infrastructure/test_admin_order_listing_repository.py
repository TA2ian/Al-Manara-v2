from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.admin_order_listing import AdminOrderListType
from app.infrastructure.persistence.admin_order_listing_repository import (
    SupabaseAdminOrderListingRepository,
)


class FakeQuery:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeResponse:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.responses[function_name])


def _row(claimed_by=None):
    return {
        "internal_order_id": str(uuid4()),
        "public_order_code": "AM-001",
        "user_telegram_id": 100,
        "wallet_id": str(uuid4()),
        "network_code": "BEP20",
        "status": "APPROVED",
        "version": 6,
        "requested_amount": "10",
        "payment_currency": "USD",
        "local_amount": "10",
        "created_at": datetime(2026, 9, 6, 10, tzinfo=timezone.utc).isoformat(),
        "total_count": 1,
        "fulfillment_claimed_by": claimed_by,
    }


@pytest.mark.asyncio
async def test_fulfillment_listing_uses_claim_aware_rpc_and_maps_owner():
    client = FakeClient({"list_admin_fulfillment_orders": FakeResponse([_row(700)])})

    page = await SupabaseAdminOrderListingRepository(client).list_orders(
        700, "primary", AdminOrderListType.FULFILLMENT, 0, 5
    )

    assert client.calls == [
        (
            "list_admin_fulfillment_orders",
            {
                "p_admin_telegram_user_id": 700,
                "p_actor_type": "primary",
                "p_page": 0,
                "p_page_size": 5,
            },
        )
    ]
    assert page.items[0].fulfillment_claimed_by == 700
    assert page.items[0].requested_amount == Decimal("10")


@pytest.mark.asyncio
async def test_non_fulfillment_listing_keeps_general_rpc_contract():
    client = FakeClient({"list_admin_orders": FakeResponse([_row()])})

    await SupabaseAdminOrderListingRepository(client).list_orders(
        700, "primary", AdminOrderListType.REVIEW, 0, 5
    )

    assert client.calls == [
        (
            "list_admin_orders",
            {
                "p_admin_telegram_user_id": 700,
                "p_actor_type": "primary",
                "p_page": 0,
                "p_page_size": 5,
                "p_list_type": "review",
            },
        )
    ]
