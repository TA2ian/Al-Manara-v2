from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.admin_session import AdminSession, AdminSessionService


@dataclass(frozen=True, slots=True)
class TelegramAdminSessionResponse:
    ok: bool
    session: AdminSession | None = None
    revoked: bool = False
    message: str = ""


class AdminSessionApplication(Protocol):
    async def create(self, admin_telegram_user_id: int, actor_type: str) -> AdminSession: ...
    async def revoke(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> bool: ...


class TelegramAdminSessionHandler:
    def __init__(self, service: AdminSessionApplication | AdminSessionService) -> None:
        self._service = service

    async def create(self, admin_user_id: int, actor_type: str) -> TelegramAdminSessionResponse:
        try:
            session = await self._service.create(admin_user_id, actor_type)
        except ValueError as exc:
            return TelegramAdminSessionResponse(False, message=str(exc))
        except PermissionError:
            return TelegramAdminSessionResponse(False, message="You are not authorized to create an admin session.")
        except RuntimeError:
            return TelegramAdminSessionResponse(False, message="The admin session could not be created. Please retry.")
        except Exception:
            return TelegramAdminSessionResponse(False, message="An unexpected error occurred. Please retry.")
        return TelegramAdminSessionResponse(True, session=session, message="Admin session created.")

    async def revoke(self, admin_user_id: int, actor_type: str, session_id: UUID) -> TelegramAdminSessionResponse:
        try:
            revoked = await self._service.revoke(admin_user_id, actor_type, session_id)
        except ValueError as exc:
            return TelegramAdminSessionResponse(False, message=str(exc))
        except PermissionError:
            return TelegramAdminSessionResponse(False, message="You are not authorized to revoke admin sessions.")
        except RuntimeError:
            return TelegramAdminSessionResponse(False, message="The admin session could not be revoked. Please retry.")
        except Exception:
            return TelegramAdminSessionResponse(False, message="An unexpected error occurred. Please retry.")
        return TelegramAdminSessionResponse(True, revoked=revoked, message="Admin session revoked." if revoked else "Admin session was already inactive.")
