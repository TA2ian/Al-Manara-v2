from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


MIN_RECEIPT_WINDOW_MINUTES = 1
DEFAULT_RECEIPT_WINDOW_MINUTES = 60
MAX_RECEIPT_WINDOW_MINUTES = 90
OPERATION = "admin_settings.receipt_window"


@dataclass(frozen=True, slots=True)
class ReceiptWindowSetting:
    minutes: int

    def __post_init__(self) -> None:
        if not MIN_RECEIPT_WINDOW_MINUTES <= self.minutes <= MAX_RECEIPT_WINDOW_MINUTES:
            raise ValueError("receipt window must be between 1 and 90 minutes")


class AdminReceiptSettingsRepository(Protocol):
    async def get_receipt_submission_window_minutes(self) -> int: ...
    async def create_confirmation(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID, operation: str, request_fingerprint: str) -> UUID: ...
    async def update_receipt_submission_window(self, admin_telegram_user_id: int, actor_type: str, confirmation_id: UUID, request_fingerprint: str, minutes: int) -> int: ...


class AdminReceiptSettingsService:
    def __init__(self, repository: AdminReceiptSettingsRepository, *, emergency_mode: bool = False) -> None:
        self._repository = repository
        self._emergency_mode = emergency_mode

    def _actor(self, actor_type: str) -> str:
        actor = actor_type.strip().lower()
        if actor not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if actor == "backup" and not self._emergency_mode:
            raise PermissionError("backup administrator requires emergency mode")
        return actor

    @staticmethod
    def _validate_admin(admin_user_id: int) -> None:
        if not isinstance(admin_user_id, int) or admin_user_id <= 0:
            raise ValueError("administrator identity is required")

    @staticmethod
    def _fingerprint(minutes: int) -> str:
        payload = json.dumps({"operation": OPERATION, "minutes": minutes}, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    async def get(self) -> ReceiptWindowSetting:
        return ReceiptWindowSetting(await self._repository.get_receipt_submission_window_minutes())

    async def request_update(self, admin_user_id: int, actor_type: str, session_id: UUID, minutes: int) -> UUID:
        actor = self._actor(actor_type)
        self._validate_admin(admin_user_id)
        if not isinstance(session_id, UUID):
            raise ValueError("administrator session is required")
        setting = ReceiptWindowSetting(minutes)
        return await self._repository.create_confirmation(
            admin_user_id, actor, session_id, OPERATION, self._fingerprint(setting.minutes)
        )

    async def confirm_update(self, admin_user_id: int, actor_type: str, confirmation_id: UUID, minutes: int) -> ReceiptWindowSetting:
        actor = self._actor(actor_type)
        self._validate_admin(admin_user_id)
        if not isinstance(confirmation_id, UUID):
            raise ValueError("confirmation is required")
        setting = ReceiptWindowSetting(minutes)
        result = await self._repository.update_receipt_submission_window(
            admin_user_id, actor, confirmation_id, self._fingerprint(setting.minutes), setting.minutes
        )
        return ReceiptWindowSetting(result)
