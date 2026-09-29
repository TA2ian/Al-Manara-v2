from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_order_review import AdminAuthorizationPort


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminAuthorizationPersistenceError(RuntimeError):
    """Raised when the authorization RPC cannot be evaluated safely."""


class SupabaseAdminAuthorizationRepository(AdminAuthorizationPort):
    def __init__(self, client: SupabaseRpcClient, *, emergency_mode: bool = False) -> None:
        self._client = client
        self._emergency_mode = emergency_mode

    def _backup_allowed(self, actor_type: str) -> bool:
        return actor_type != "backup" or self._emergency_mode

    async def authorize(self, telegram_user_id: int, actor_type: str) -> bool:
        normalized_actor = actor_type.strip().lower()
        if normalized_actor not in {"primary", "backup"}:
            return False
        if not self._backup_allowed(normalized_actor):
            return False
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "authorize_admin_order_review",
                    {
                        "p_telegram_user_id": telegram_user_id,
                        "p_actor_type": normalized_actor,
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminAuthorizationPersistenceError("admin authorization RPC failed") from exc
        error = getattr(response, "error", None)
        if error:
            raise AdminAuthorizationPersistenceError("admin authorization RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminAuthorizationPersistenceError("admin authorization RPC returned invalid data")
        value = data[0].get("authorize_admin_order_review")
        if not isinstance(value, bool):
            raise AdminAuthorizationPersistenceError("admin authorization RPC returned invalid authorization value")
        return value

    async def resolve_actor_type(self, telegram_user_id: int) -> str | None:
        if not isinstance(telegram_user_id, int) or telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "resolve_admin_actor_type",
                    {"p_telegram_user_id": telegram_user_id},
                ).execute
            )
        except Exception as exc:
            raise AdminAuthorizationPersistenceError("admin actor resolution RPC failed") from exc
        if getattr(response, "error", None):
            raise AdminAuthorizationPersistenceError("admin actor resolution RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminAuthorizationPersistenceError("admin actor resolution RPC returned invalid data")
        if len(data) == 0:
            return None
        if len(data) != 1 or not isinstance(data[0], dict):
            raise AdminAuthorizationPersistenceError("admin actor resolution RPC returned invalid result count")
        value = data[0].get("actor_type")
        if value not in {"primary", "backup"}:
            raise AdminAuthorizationPersistenceError("admin actor resolution RPC returned invalid actor type")
        return value

    async def validate_session(self, telegram_user_id: int, actor_type: str, session_id: UUID) -> bool:
        if not isinstance(telegram_user_id, int) or telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        normalized_actor = actor_type.strip().lower()
        if normalized_actor not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if normalized_actor == "backup" and not self._emergency_mode:
            return False
        if not isinstance(session_id, UUID):
            raise ValueError("session identity is required")
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "validate_admin_session",
                    {
                        "p_admin_telegram_user_id": telegram_user_id,
                        "p_actor_type": normalized_actor,
                        "p_session_id": str(session_id),
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminAuthorizationPersistenceError("admin session validation RPC failed") from exc
        if getattr(response, "error", None):
            raise AdminAuthorizationPersistenceError("admin session validation RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminAuthorizationPersistenceError("admin session validation RPC returned invalid data")
        value = data[0].get("validate_admin_session")
        if not isinstance(value, bool):
            raise AdminAuthorizationPersistenceError("admin session validation RPC returned invalid result")
        return value
