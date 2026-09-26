from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_payment_account import AdminPaymentAccount, AdminPaymentAccountRepository
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminPaymentAccountPersistenceError(RuntimeError):
    """Raised when admin payment account persistence returns invalid data or fails."""


class SupabaseAdminPaymentAccountRepository(AdminPaymentAccountRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def create_confirmation(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
        operation: str,
        request_fingerprint: str,
    ) -> UUID:
        rows = await self._rpc(
            "create_admin_action_confirmation",
            {
                "p_admin_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_session_id": str(session_id),
                "p_operation": operation,
                "p_request_fingerprint": request_fingerprint,
            },
        )
        if len(rows) != 1:
            raise AdminPaymentAccountPersistenceError(
                "admin action confirmation returned invalid row count"
            )
        try:
            return UUID(str(rows[0]["confirmation_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminPaymentAccountPersistenceError(
                "admin action confirmation returned invalid id"
            ) from exc

    async def list(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        session_id: UUID,
    ) -> list[AdminPaymentAccount]:
        rows = await self._rpc(
            "list_admin_payment_accounts",
            {
                "p_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_session_id": str(session_id),
            },
        )
        return [self._parse(row) for row in rows]

    async def upsert(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
    ) -> AdminPaymentAccount:
        rows = await self._rpc(
            "upsert_admin_payment_account",
            {
                "p_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_currency": currency.value,
                "p_account_name": setup.recipient_name,
                "p_account_number": setup.receiving_address,
                "p_qr_image_file_id": setup.qr_image_file_id,
                "p_session_id": str(session_id),
                "p_confirmation_id": str(confirmation_id),
                "p_request_fingerprint": request_fingerprint,
            },
        )
        if len(rows) != 1:
            raise AdminPaymentAccountPersistenceError("payment account upsert returned invalid row count")
        return self._parse(row=rows[0])

    async def set_active(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
    ) -> AdminPaymentAccount:
        rows = await self._rpc(
            "set_admin_payment_account_active",
            {
                "p_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_currency": currency.value,
                "p_is_active": is_active,
                "p_session_id": str(session_id),
                "p_confirmation_id": str(confirmation_id),
                "p_request_fingerprint": request_fingerprint,
            },
        )
        if len(rows) != 1:
            raise AdminPaymentAccountPersistenceError("payment account status update returned invalid row count")
        return self._parse(row=rows[0])

    async def _rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(self._client.rpc(function_name, params).execute)
        except Exception as exc:
            raise AdminPaymentAccountPersistenceError(
                f"admin payment account RPC failed: {function_name}"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            raise AdminPaymentAccountPersistenceError(_error_message(error))
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminPaymentAccountPersistenceError(
                f"RPC returned invalid data: {function_name}"
            )
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _parse(row: dict[str, Any]) -> AdminPaymentAccount:
        try:
            return AdminPaymentAccount(
                id=str(row["id"]),
                currency=CurrencyCode(str(row["currency"])),
                account_name=str(row["account_name"]),
                account_number=str(row["account_number"]),
                qr_image_file_id=str(row["qr_image_file_id"]),
                is_active=bool(row["is_active"]),
                updated_at=_parse_datetime(row["updated_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminPaymentAccountPersistenceError("invalid admin payment account payload") from exc


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("invalid updated_at")
    if result.tzinfo is None:
        raise ValueError("updated_at must be timezone-aware")
    return result


def _error_message(error: Any) -> str:
    if isinstance(error, str):
        return error.strip()
    message = getattr(error, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    if isinstance(error, dict):
        value = error.get("message") or error.get("details") or error.get("hint")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(error).strip() or "unknown persistence error"
