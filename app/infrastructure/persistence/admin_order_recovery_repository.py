from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_order_recovery import AdminOrderRecoveryRepository, AdminOrderRecoveryResult


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminOrderRecoveryPersistenceError(RuntimeError):
    pass


class SupabaseAdminOrderRecoveryRepository(AdminOrderRecoveryRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def recover_to_review(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
        reason: str,
        idempotency_key: str,
    ) -> AdminOrderRecoveryResult:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "admin_recover_order_to_review",
                    {
                        "p_order_id": str(internal_order_id),
                        "p_expected_version": expected_version,
                        "p_admin_telegram_user_id": admin_telegram_user_id,
                        "p_actor_type": actor_type,
                        "p_session_id": str(session_id),
                        "p_confirmation_id": str(confirmation_id),
                        "p_request_fingerprint": request_fingerprint,
                        "p_reason": reason,
                        "p_idempotency_key": idempotency_key,
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminOrderRecoveryPersistenceError("order recovery RPC failed") from exc

        error = getattr(response, "error", None)
        if error:
            raise AdminOrderRecoveryPersistenceError(self._error_message(error))
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminOrderRecoveryPersistenceError("invalid order recovery response")
        row = data[0]
        try:
            result = AdminOrderRecoveryResult(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=str(row["status"]).strip().upper(),
                version=int(row["version"]),
                replayed=bool(row["replayed"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminOrderRecoveryPersistenceError("invalid order recovery payload") from exc
        if result.internal_order_id != internal_order_id or result.status != "UNDER_REVIEW":
            raise AdminOrderRecoveryPersistenceError("order recovery returned inconsistent state")
        return result

    @staticmethod
    def _error_message(error: Any) -> str:
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "order recovery failed"
