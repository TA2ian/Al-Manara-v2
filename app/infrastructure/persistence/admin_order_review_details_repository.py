from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_order_review_details import (
    AdminOrderReviewDetails,
    AdminOrderReviewDetailsRepository,
)


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminOrderReviewDetailsPersistenceError(RuntimeError):
    pass


class SupabaseAdminOrderReviewDetailsRepository(AdminOrderReviewDetailsRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_details(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        order_id: UUID,
        session_id: UUID,
    ) -> AdminOrderReviewDetails:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "get_admin_order_review_details",
                    {
                        "p_admin_telegram_user_id": admin_telegram_user_id,
                        "p_actor_type": actor_type,
                        "p_order_id": str(order_id),
                        "p_session_id": str(session_id),
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminOrderReviewDetailsPersistenceError("admin review details RPC failed") from exc
        if getattr(response, "error", None):
            raise AdminOrderReviewDetailsPersistenceError("admin review details RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise AdminOrderReviewDetailsPersistenceError("admin review details RPC returned invalid data")
        row = data[0]
        try:
            submitted_at = row.get("receipt_submitted_at")
            if isinstance(submitted_at, str):
                submitted_at = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
            if submitted_at is not None and (
                not isinstance(submitted_at, datetime) or submitted_at.tzinfo is None
            ):
                raise ValueError("receipt timestamp must be timezone-aware")
            return AdminOrderReviewDetails(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=str(row["status"]),
                version=int(row["version"]),
                user_telegram_id=int(row["user_telegram_id"]),
                network_code=str(row["network_code"]),
                requested_amount=Decimal(str(row["requested_amount"])) if row.get("requested_amount") is not None else None,
                payment_currency=str(row["payment_currency"]) if row.get("payment_currency") is not None else None,
                local_amount=Decimal(str(row["local_amount"])) if row.get("local_amount") is not None else None,
                receipt_submission_id=UUID(str(row["receipt_submission_id"])) if row.get("receipt_submission_id") else None,
                receipt_attempt_number=int(row["receipt_attempt_number"]) if row.get("receipt_attempt_number") is not None else None,
                receipt_processing_status=str(row["receipt_processing_status"]) if row.get("receipt_processing_status") is not None else None,
                receipt_linkage_status=str(row["receipt_linkage_status"]) if row.get("receipt_linkage_status") is not None else None,
                receipt_telegram_file_id=str(row["receipt_telegram_file_id"]) if row.get("receipt_telegram_file_id") else None,
                receipt_mime_type=str(row["receipt_mime_type"]) if row.get("receipt_mime_type") else None,
                receipt_submitted_at=submitted_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminOrderReviewDetailsPersistenceError("invalid admin review details payload") from exc
