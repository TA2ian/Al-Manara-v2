import pytest

from app.application.customer_order_listing import (
    CustomerOrderListingService,
    CustomerOrderPage,
    ListCustomerOrdersCommand,
)


class FakeRepository:
    def __init__(self):
        self.calls = []

    async def list_orders(self, *args):
        self.calls.append(args)
        return CustomerOrderPage((), args[1], args[2], 0)


@pytest.mark.asyncio
async def test_listing_forwards_customer_scoped_pagination():
    repository = FakeRepository()
    service = CustomerOrderListingService(repository)

    page = await service.list(ListCustomerOrdersCommand(123, 2, 10))

    assert page.page == 2
    assert repository.calls == [(123, 2, 10)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command, message",
    [
        (ListCustomerOrdersCommand(0), "customer identity"),
        (ListCustomerOrdersCommand(1, -1), "page must"),
        (ListCustomerOrdersCommand(1, 0, 0), "page size"),
        (ListCustomerOrdersCommand(1, 0, 51), "page size"),
    ],
)
async def test_listing_rejects_invalid_input_before_persistence(command, message):
    repository = FakeRepository()
    service = CustomerOrderListingService(repository)

    with pytest.raises(ValueError, match=message):
        await service.list(command)

    assert repository.calls == []