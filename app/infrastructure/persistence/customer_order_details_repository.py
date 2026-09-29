from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.application.customer_order_details import CustomerOrderDetails, CustomerOrderDetailsRepository
from app.domain.order_status import OrderStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class CustomerOrderDetailsPersistenceError(RuntimeError):
    pass


class SupabaseCustomerOrderDetailsRepository(CustomerOrderDetailsRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_order(self, customer_telegram_user_id: int, public_order_code: str) -> CustomerOrderDetails | None:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "get_customer_order_details",
                    {
                        "p_telegram_user_id": customer_telegram_user_id,
                        "p_public_order_code": public_order_code,
                    },
                ).execute
            )
        except Exception as exc:
            raise CustomerOrderDetailsPersistenceError("customer order details RPC failed") from exc
        if getattr(response, "error", None):
            raise CustomerOrderDetailsPersistenceError("customer order details RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise CustomerOrderDetailsPersistenceError("customer order details RPC returned invalid data")
        if not data:
            return None
        if len(data) != 1 or not isinstance(data[0], dict):
            raise CustomerOrderDetailsPersistenceError("customer order details RPC returned invalid rows")
        row = data[0]
        try:
            created_at = row["created_at"]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if not isinstance(created_at, datetime) or created_at.tzinfo is None:
                raise ValueError("created_at must be timezone-aware")
            return CustomerOrderDetails(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=OrderStatus(str(row["status"]).strip().upper()),
                version=int(row["version"]),
                network_code=str(row["network_code"]),
                requested_amount=Decimal(str(row["requested_amount"])) if row.get("requested_amount") is not None else None,
                payment_currency=str(row["payment_currency"]) if row.get("payment_currency") is not None else None,
                local_amount=Decimal(str(row["local_amount"])) if row.get("local_amount") is not None else None,
                created_at=created_at,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise CustomerOrderDetailsPersistenceError("invalid customer order details payload") from exc
