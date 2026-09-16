from __future__ import annotations

import asyncio
from typing import Any, Protocol

from app.application.admin_order_review import AdminAuthorizationPort


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminAuthorizationPersistenceError(RuntimeError):
    """Raised when the authorization RPC cannot be evaluated safely."""


class SupabaseAdminAuthorizationRepository(AdminAuthorizationPort):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def authorize(self, telegram_user_id: int, actor_type: str) -> bool:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "authorize_admin_order_review",
                    {
                        "p_telegram_user_id": telegram_user_id,
                        "p_actor_type": actor_type.strip().lower(),
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminAuthorizationPersistenceError(
                "admin authorization RPC failed"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            raise AdminAuthorizationPersistenceError(
                "admin authorization RPC returned an error"
            )

        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminAuthorizationPersistenceError(
                "admin authorization RPC returned invalid data"
            )

        value = data[0].get("authorize_admin_order_review")
        if not isinstance(value, bool):
            raise AdminAuthorizationPersistenceError(
                "admin authorization RPC returned invalid authorization value"
            )
        return value

    async def resolve_actor_type(self, telegram_user_id: int) -> str | None:
        """Resolve the actor type from the DB; never trust Telegram/user input for it."""
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
            raise AdminAuthorizationPersistenceError(
                "admin actor resolution RPC failed"
            ) from exc

        if getattr(response, "error", None):
            raise AdminAuthorizationPersistenceError(
                "admin actor resolution RPC returned an error"
            )

        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminAuthorizationPersistenceError(
                "admin actor resolution RPC returned invalid data"
            )
        if len(data) == 0:
            return None
        if len(data) != 1 or not isinstance(data[0], dict):
            raise AdminAuthorizationPersistenceError(
                "admin actor resolution RPC returned invalid result count"
            )
        value = data[0].get("actor_type")
        if value not in {"primary", "backup"}:
            raise AdminAuthorizationPersistenceError(
                "admin actor resolution RPC returned invalid actor type"
            )
        return value
