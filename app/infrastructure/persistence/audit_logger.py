from __future__ import annotations

import asyncio
from typing import Any, Mapping, Protocol
from uuid import UUID


class SupabaseTableQuery(Protocol):
    def insert(self, values: dict[str, Any]) -> Any: ...
    def execute(self) -> Any: ...


class SupabaseTableClient(Protocol):
    def table(self, table_name: str) -> SupabaseTableQuery: ...


class AuditPersistenceError(RuntimeError):
    """Raised when an audit record cannot be durably appended."""


class SupabaseAuditLogger:
    """Append-only audit adapter backed by the canonical audit_logs table."""

    def __init__(self, client: SupabaseTableClient) -> None:
        self._client = client

    async def record(
        self,
        event: str,
        *,
        actor_user_id: int,
        actor_kind: str,
        target_id: UUID,
        metadata: Mapping[str, object],
        actor_type: str | None = None,
        target_type: str = "wallet",
    ) -> None:
        if not isinstance(event, str) or not event.strip():
            raise ValueError("audit event must be non-empty")
        if not isinstance(actor_user_id, int) or isinstance(actor_user_id, bool) or actor_user_id <= 0:
            raise ValueError("audit actor must be a positive integer")
        if actor_kind not in {"customer", "admin"}:
            raise ValueError("invalid audit actor kind")
        if actor_kind == "admin" and actor_type not in {"primary", "backup"}:
            raise ValueError("admin audit actor type is required")
        if actor_kind == "customer" and actor_type is not None:
            raise ValueError("customer audit actor type must be omitted")
        if not isinstance(target_id, UUID):
            raise ValueError("audit target must be a UUID")
        if not isinstance(target_type, str) or not target_type.strip():
            raise ValueError("audit target type must be non-empty")
        if not isinstance(metadata, Mapping):
            raise ValueError("audit metadata must be a mapping")

        payload = {
            "actor_telegram_user_id": actor_user_id,
            "actor_kind": actor_kind,
            "actor_type": actor_type,
            "action": event.strip(),
            "target_type": target_type.strip(),
            "target_id": str(target_id),
            "metadata": dict(metadata),
        }
        try:
            response = await asyncio.to_thread(
                lambda: self._client.table("audit_logs").insert(payload).execute()
            )
        except Exception as exc:
            raise AuditPersistenceError("audit log append failed") from exc

        error = getattr(response, "error", None)
        if error:
            raise AuditPersistenceError("audit log append failed")
