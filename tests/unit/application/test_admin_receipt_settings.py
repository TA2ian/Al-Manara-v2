import pytest
from uuid import uuid4

from app.application.admin_receipt_settings import (
    AdminReceiptSettingsService,
    MAX_RECEIPT_WINDOW_MINUTES,
    DEFAULT_RECEIPT_WINDOW_MINUTES,
)


class Repo:
    def __init__(self):
        self.updated = None

    async def get_receipt_submission_window_minutes(self):
        return DEFAULT_RECEIPT_WINDOW_MINUTES

    async def create_confirmation(self, admin_telegram_user_id, actor_type, session_id, operation, request_fingerprint):
        self.confirmation = (admin_telegram_user_id, actor_type, session_id, operation, request_fingerprint)
        return uuid4()

    async def update_receipt_submission_window(self, admin_telegram_user_id, actor_type, confirmation_id, request_fingerprint, minutes):
        self.updated = minutes
        return minutes


@pytest.mark.asyncio
async def test_default_window_is_60_minutes():
    setting = await AdminReceiptSettingsService(Repo()).get()
    assert setting.minutes == 60


@pytest.mark.asyncio
async def test_admin_can_explicitly_extend_to_90_minutes():
    repo = Repo()
    service = AdminReceiptSettingsService(repo)
    confirmation = await service.request_update(123, "primary", uuid4(), 90)
    assert confirmation
    updated = await service.confirm_update(123, "primary", confirmation, 90)
    assert updated.minutes == MAX_RECEIPT_WINDOW_MINUTES
    assert repo.updated == 90


@pytest.mark.asyncio
async def test_backup_requires_emergency_mode():
    with pytest.raises(PermissionError):
        await AdminReceiptSettingsService(Repo()).request_update(123, "backup", uuid4(), 60)
