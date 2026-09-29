from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminReceiptSettingsPersistenceError(RuntimeError):
    pass


class SupabaseAdminReceiptSettingsRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_receipt_submission_window_minutes(self) -> int:
        response = await asyncio.to_thread(self._client.rpc("get_receipt_submission_window", {}).execute)
        error = getattr(response, "error", None)
        if error:
            raise AdminReceiptSettingsPersistenceError("settings read failed")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1:
            raise AdminReceiptSettingsPersistenceError("invalid settings response")
        try:
            value = int(data[0]["receipt_submission_window_minutes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminReceiptSettingsPersistenceError("invalid receipt window") from exc
        if not 1 <= value <= 90:
            raise AdminReceiptSettingsPersistenceError("receipt window outside allowed range")
        return value

    async def create_confirmation(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID, operation: str, request_fingerprint: str) -> UUID:
        response = await asyncio.to_thread(self._client.rpc(
            "create_admin_action_confirmation",
            {"p_admin_telegram_user_id": admin_telegram_user_id, "p_actor_type": actor_type,
             "p_session_id": str(session_id), "p_operation": operation, "p_request_fingerprint": request_fingerprint}
        ).execute)
        error = getattr(response, "error", None)
        if error:
            raise AdminReceiptSettingsPersistenceError("confirmation creation failed")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1:
            raise AdminReceiptSettingsPersistenceError("invalid confirmation response")
        try:
            return UUID(str(data[0]["confirmation_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminReceiptSettingsPersistenceError("invalid confirmation id") from exc

    async def update_receipt_submission_window(self, admin_telegram_user_id: int, actor_type: str, confirmation_id: UUID, request_fingerprint: str, minutes: int) -> int:
        response = await asyncio.to_thread(self._client.rpc(
            "update_receipt_submission_window",
            {"p_admin_telegram_user_id": admin_telegram_user_id, "p_actor_type": actor_type,
             "p_confirmation_id": str(confirmation_id), "p_request_fingerprint": request_fingerprint,
             "p_minutes": minutes}
        ).execute)
        error = getattr(response, "error", None)
        if error:
            raise AdminReceiptSettingsPersistenceError("receipt window update failed")
        value = getattr(response, "data", None)
        if not isinstance(value, int) or not 1 <= value <= 90:
            raise AdminReceiptSettingsPersistenceError("invalid updated receipt window")
        return value
