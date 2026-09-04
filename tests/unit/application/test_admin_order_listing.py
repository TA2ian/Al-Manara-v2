from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.admin_order_listing import (
    AdminOrderListType,
    AdminOrderPage,
    AdminOrderListingService,
    ListAdminOrdersCommand,
)


class FakeRepository:
    def __init__(self):
        self.calls = []

    async def list_orders(self, *args):
        self.calls.append(args)
        return AdminOrderPage((), args[3], args[4], 0)


@pytest.mark.asyncio
async def test_listing_normalizes_actor_and_type():
    repo = FakeRepository()
    service = AdminOrderListingService(repo)
    result = await service.list(ListAdminOrdersCommand(100, " PRIMARY ", " REVIEW ", 2, 10))
    assert result.page == 2
    assert repo.calls == [(100, "primary", AdminOrderListType.REVIEW, 2, 10)]


@pytest.mark.asyncio
async def test_listing_rejects_invalid_paging_before_persistence():
    repo = FakeRepository()
    service = AdminOrderListingService(repo)
    with pytest.raises(ValueError, match="page"):
        await service.list(ListAdminOrdersCommand(100, "primary", page=-1))
    assert repo.calls == []
