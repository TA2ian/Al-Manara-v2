from uuid import uuid4

import pytest

from app.application.admin_receipt_recheck import AdminReceiptRecheckCommand, AdminReceiptRecheckService


class FakeAuth:
    async def authorize(self, *args):
        return True


class FakeVerification:
    async def verify(self, request):
        class Output:
            evidence = "evidence"
        self.request = request
        return Output()


@pytest.mark.asyncio
async def test_recheck_is_read_only_and_authorized() -> None:
    verification = FakeVerification()
    service = AdminReceiptRecheckService(FakeAuth(), verification)
    extracted = object()
    result = await service.recheck(
        AdminReceiptRecheckCommand(uuid4(), 100, "primary", uuid4(), extracted)
    )
    assert result == "evidence"
    assert verification.request.extracted is extracted


@pytest.mark.asyncio
async def test_recheck_rejects_unknown_actor() -> None:
    with pytest.raises(ValueError, match="invalid admin actor"):
        await AdminReceiptRecheckService(FakeAuth(), FakeVerification()).recheck(
            AdminReceiptRecheckCommand(uuid4(), 100, "operator", uuid4(), object())
        )
