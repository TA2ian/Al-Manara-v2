from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.domain.receipt_verification_context import ReceiptVerificationContext


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class ReceiptVerificationSnapshotPersistenceError(RuntimeError):
    """Raised when the authoritative receipt snapshot boundary is invalid."""


class SupabaseReceiptVerificationSnapshotRepository:
    """Reads the immutable order-financial snapshot used by receipt verification."""

    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_receipt_verification_context(
        self,
        order_id: UUID,
    ) -> ReceiptVerificationContext | None:
        if not isinstance(order_id, UUID):
            raise ValueError("order_id must be a UUID")

        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "get_receipt_verification_snapshot",
                    {"p_order_id": str(order_id)},
                ).execute
            )
        except Exception as exc:
            raise ReceiptVerificationSnapshotPersistenceError(
                "receipt verification snapshot RPC failed"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            raise ReceiptVerificationSnapshotPersistenceError(
                "receipt verification snapshot RPC returned an error"
            )

        rows = getattr(response, "data", None)
        if not isinstance(rows, list):
            raise ReceiptVerificationSnapshotPersistenceError(
                "receipt verification snapshot RPC returned invalid data"
            )
        if not rows:
            return None
        if len(rows) != 1 or not isinstance(rows[0], dict):
            raise ReceiptVerificationSnapshotPersistenceError(
                "receipt verification snapshot RPC returned invalid row count"
            )

        return self._map_context(rows[0], order_id)

    @staticmethod
    def _map_context(
        row: dict[str, Any],
        expected_order_id: UUID,
    ) -> ReceiptVerificationContext:
        try:
            persisted_order_id = UUID(str(row["order_id"]))
            if persisted_order_id != expected_order_id:
                raise ValueError("order id mismatch")

            return ReceiptVerificationContext(
                order_id=persisted_order_id,
                payment_currency=str(row["payment_currency"]),
                expected_payment_amount=Decimal(str(row["expected_payment_amount"])),
                exchange_rate=(
                    Decimal(str(row["exchange_rate"]))
                    if row.get("exchange_rate") is not None
                    else None
                ),
                fee_percent=Decimal(str(row["fee_percent"])),
                rounding_policy_version=str(row["rounding_policy_version"]),
                network_code=str(row["network_code"]),
                wallet_address=str(row["wallet_address"]),
                expected_reference=(
                    str(row["expected_reference"])
                    if row.get("expected_reference") is not None
                    else None
                ),
                tolerance=Decimal(str(row["tolerance"])),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ReceiptVerificationSnapshotPersistenceError(
                "invalid receipt verification snapshot payload"
            ) from exc
