from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AdminSession:
    session_id: UUID
    expires_at: datetime


class AdminSessionRepository(Protocol):
    async def create(self, admin_telegram_user_id: int, actor_type: str) -> AdminSession: ...
    async def revoke(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> bool: ...


class AdminSessionService:
    def __init__(self, repository: AdminSessionRepository) -> None:
        self._repository = repository

    @staticmethod
    def _validate_admin(admin_telegram_user_id: int, actor_type: str) -> str:
        if admin_telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        normalized = actor_type.strip().lower()
        if normalized not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        return normalized

    async def create(self, admin_telegram_user_id: int, actor_type: str) -> AdminSession:
        return await self._repository.create(admin_telegram_user_id, self._validate_admin(admin_telegram_user_id, actor_type))

    async def revoke(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> bool:
        return await self._repository.revoke(admin_telegram_user_id, self._validate_admin(admin_telegram_user_id, actor_type), session_id)
