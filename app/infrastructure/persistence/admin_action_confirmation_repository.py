from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminActionConfirmationPersistenceError(RuntimeError):
    pass


class SupabaseAdminActionConfirmationRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def create(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID, operation: str, request_fingerprint: str) -> UUID:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "create_admin_action_confirmation",
                    {
                        "p_admin_telegram_user_id": admin_telegram_user_id,
                        "p_actor_type": actor_type,
                        "p_session_id": str(session_id),
                        "p_operation": operation,
                        "p_request_fingerprint": request_fingerprint,
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminActionConfirmationPersistenceError("confirmation RPC failed") from exc
        error = getattr(response, "error", None)
        if error:
            raise AdminActionConfirmationPersistenceError("confirmation RPC rejected the request")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminActionConfirmationPersistenceError("invalid confirmation response")
        try:
            return UUID(str(data[0]["confirmation_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminActionConfirmationPersistenceError("invalid confirmation id") from exc
