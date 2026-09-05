from uuid import uuid4

import pytest

from app.application.customer_identity import CustomerIdentityService


class FakeRepository:
    def __init__(self):
        self.calls = []

    async def list_pending(self, *args):
        self.calls.append(("list", args))
        return ()

    async def approve(self, *args):
        self.calls.append(("approve", args))

    async def reject(self, *args):
        self.calls.append(("reject", args))


@pytest.mark.asyncio
async def test_identity_review_accepts_only_primary_administrator():
    repository = FakeRepository()
    service = CustomerIdentityService(repository)

    await service.approve(123, "primary", uuid4())
    with pytest.raises(ValueError, match="role"):
        await service.list_pending(123, "backup")

    assert repository.calls[0][0] == "approve"
    assert repository.calls[0][1][1] == "primary"


@pytest.mark.asyncio
async def test_identity_rejection_trims_valid_reason_before_persistence():
    repository = FakeRepository()
    service = CustomerIdentityService(repository)

    await service.reject(123, "primary", uuid4(), "  mismatched details  ")

    assert repository.calls[0][1][-1] == "mismatched details"