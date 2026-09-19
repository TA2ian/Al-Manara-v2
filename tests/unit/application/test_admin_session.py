from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.admin_session import AdminSession, AdminSessionService


class FakeRepository:
    def __init__(self):
        self.calls = []

    async def create(self, *args):
        self.calls.append(("create", *args))
        return AdminSession(uuid4(), datetime.now(timezone.utc))

    async def revoke(self, *args):
        self.calls.append(("revoke", *args))
        return True


@pytest.mark.asyncio
async def test_session_service_normalizes_actor_type():
    repo = FakeRepository()
    service = AdminSessionService(repo)
    await service.create(100, " PRIMARY ")
    assert repo.calls == [("create", 100, "primary")]


@pytest.mark.asyncio
async def test_session_service_rejects_invalid_admin():
    repo = FakeRepository()
    service = AdminSessionService(repo)
    with pytest.raises(ValueError, match="administrator identity"):
        await service.create(0, "primary")
    assert repo.calls == []
