from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.receipt_attempt import ReceiptAttemptStatus, ReceiptInputType
from app.infrastructure.persistence.receipt_attempt_repository import (
    ReceiptPersistenceConflictError,
    ReceiptPersistenceError,
    ReceiptPersistenceNotFoundError,
    SupabaseReceiptAttemptRepository,
)


@dataclass
class FakeResponse:
    data: list[dict] | None = None
    error: object | None = None


class FakeQuery:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.execute_calls = 0

    def execute(self) -> FakeResponse:
        self.execute_calls += 1
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.function_name = None
        self.params = None
        self.query = FakeQuery(response)

    def rpc(self, function_name: str, params: dict) -> FakeQuery:
        self.function_name = function_name
        self.params = params
        return self.query


@pytest.mark.asyncio
async def test_reserve_maps_unified_image_payload():
    order_id, submission_id = uuid4(), uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(FakeResponse(data=[{
        "submission_id": str(submission_id), "internal_order_id": str(order_id),
        "attempt_number": 1, "input_type": "IMAGE", "transaction_reference": None,
        "telegram_file_id": "file-1", "mime_type": "image/png",
        "submitted_at": submitted_at.isoformat(), "processing_status": "PROCESSING", "replayed": False,
    }]))

    reservation = await SupabaseReceiptAttemptRepository(client).reserve_next_attempt(
        order_id=order_id, telegram_user_id=7001, idempotency_key=" update-123 ",
        submitted_at=submitted_at, input_type=ReceiptInputType.IMAGE,
        transaction_reference=None, mime_type="image/png", telegram_file_id=" file-1 ",
    )

    assert client.params == {
        "p_order_id": str(order_id), "p_telegram_user_id": 7001,
        "p_idempotency_key": "update-123", "p_input_type": "IMAGE",
        "p_transaction_reference": None, "p_telegram_file_id": "file-1",
        "p_mime_type": "image/png", "p_submitted_at": submitted_at.isoformat(),
    }
    assert reservation.replayed is False
    assert reservation.attempt.input_type is ReceiptInputType.IMAGE
    assert reservation.attempt.transaction_reference is None


@pytest.mark.asyncio
async def test_reserve_maps_unified_text_payload():
    order_id = uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(FakeResponse(data=[{
        "submission_id": str(uuid4()), "internal_order_id": str(order_id),
        "attempt_number": 1, "input_type": "TEXT", "transaction_reference": "SC-123456",
        "telegram_file_id": None, "mime_type": None,
        "submitted_at": submitted_at.isoformat(), "processing_status": "PROCESSING", "replayed": False,
    }]))

    reservation = await SupabaseReceiptAttemptRepository(client).reserve_next_attempt(
        order_id, 7001, "update-123", submitted_at, ReceiptInputType.TEXT,
        "SC-123456", None, None,
    )

    assert reservation.attempt.input_type is ReceiptInputType.TEXT
    assert reservation.attempt.transaction_reference == "SC-123456"
    assert reservation.attempt.telegram_file_id is None
    assert reservation.attempt.mime_type is None


@pytest.mark.asyncio
async def test_replayed_reservation_is_mapped():
    order_id = uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(FakeResponse(data=[{
        "submission_id": str(uuid4()), "internal_order_id": str(order_id),
        "attempt_number": 2, "input_type": "TEXT", "transaction_reference": "SC-2",
        "telegram_file_id": None, "mime_type": None,
        "submitted_at": submitted_at.isoformat(), "processing_status": "FAILED",
        "failure_reason": "previous failure", "replayed": True,
    }]))

    reservation = await SupabaseReceiptAttemptRepository(client).reserve_next_attempt(
        order_id, 7001, "update-123", submitted_at, ReceiptInputType.TEXT, "SC-2", None, None
    )
    assert reservation.replayed is True
    assert reservation.attempt.status is ReceiptAttemptStatus.FAILED
    assert reservation.attempt.transaction_reference == "SC-2"


@pytest.mark.asyncio
async def test_finalize_maps_unified_payload():
    order_id, submission_id = uuid4(), uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(FakeResponse(data=[{
        "submission_id": str(submission_id), "internal_order_id": str(order_id),
        "attempt_number": 1, "input_type": "TEXT", "transaction_reference": "SC-123",
        "telegram_file_id": None, "mime_type": None,
        "submitted_at": submitted_at.isoformat(), "processing_status": "SUCCEEDED",
        "linkage_status": "LINKED", "failure_reason": None,
    }]))

    result = await SupabaseReceiptAttemptRepository(client).finalize(submission_id, ReceiptAttemptStatus.VERIFIED)

    assert result.status is ReceiptAttemptStatus.VERIFIED
    assert result.input_type is ReceiptInputType.TEXT
    assert result.transaction_reference == "SC-123"


@pytest.mark.asyncio
async def test_finalize_rejects_processing_status():
    with pytest.raises(ValueError, match="PROCESSING cannot be finalized"):
        await SupabaseReceiptAttemptRepository(FakeClient(FakeResponse(data=[]))).finalize(uuid4(), ReceiptAttemptStatus.PROCESSING)


@pytest.mark.asyncio
async def test_empty_rpc_result_is_not_silently_accepted():
    with pytest.raises(ReceiptPersistenceNotFoundError, match="returned no row"):
        await SupabaseReceiptAttemptRepository(FakeClient(FakeResponse(data=[]))).finalize(uuid4(), ReceiptAttemptStatus.VERIFIED)


@pytest.mark.asyncio
async def test_database_conflict_is_mapped():
    client = FakeClient(FakeResponse(error={"message": "receipt attempt limit reached"}))
    with pytest.raises(ReceiptPersistenceConflictError, match="attempt limit"):
        await SupabaseReceiptAttemptRepository(client).reserve_next_attempt(
            uuid4(), 7001, "update-123", datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc),
            ReceiptInputType.IMAGE, None, "image/png", "file-1"
        )


@pytest.mark.asyncio
async def test_unknown_database_error_is_wrapped():
    client = FakeClient(FakeResponse(error={"message": "permission denied"}))
    with pytest.raises(ReceiptPersistenceError, match="permission denied"):
        await SupabaseReceiptAttemptRepository(client).reserve_next_attempt(
            uuid4(), 7001, "update-123", datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc),
            ReceiptInputType.IMAGE, None, "image/png", "file-1"
        )
