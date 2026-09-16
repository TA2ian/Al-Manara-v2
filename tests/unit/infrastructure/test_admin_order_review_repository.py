from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.order_status import OrderStatus
from app.infrastructure.persistence.admin_order_review_repository import (
    AdminOrderReviewPersistenceError,
    SupabaseAdminOrderReviewRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class Response:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeQuery(self.response)


@pytest.mark.asyncio
async def test_maps_admin_review_rpc_result_and_session() -> None:
    order_id = uuid4()
    session_id = uuid4()
    transitioned_at = datetime.now(timezone.utc)
    client = FakeClient(
        Response(
            [{
                "internal_order_id": str(order_id),
                "public_order_code": "ORD-REVIEW05",
                "status": "APPROVED",
                "version": 4,
                "state_before": "UNDER_REVIEW",
                "state_after": "APPROVED",
                "transitioned_at": transitioned_at.isoformat(),
            }]
        )
    )

    result = await SupabaseAdminOrderReviewRepository(client).transition(
        order_id,
        OrderStatus.APPROVED,
        3,
        1001,
        "primary",
        "review-5",
        None,
        session_id,
    )

    assert result.order.internal_order_id == order_id
    assert result.state_before is OrderStatus.UNDER_REVIEW
    assert result.state_after is OrderStatus.APPROVED
    assert result.order.version == 4
    assert client.calls[0][0] == "admin_review_order_transition_idempotent"
    assert client.calls[0][1]["p_session_id"] == str(session_id)
    assert client.calls[0][1]["p_actor_type"] == "primary"


@pytest.mark.asyncio
async def test_rejects_inconsistent_admin_review_payload() -> None:
    order_id = uuid4()
    client = FakeClient(
        Response(
            [{
                "internal_order_id": str(order_id),
                "public_order_code": "ORD-REVIEW06",
                "status": "REJECTED",
                "version": 2,
                "state_before": "UNDER_REVIEW",
                "state_after": "APPROVED",
                "transitioned_at": datetime.now(timezone.utc).isoformat(),
            }]
        )
    )

    with pytest.raises(AdminOrderReviewPersistenceError):
        await SupabaseAdminOrderReviewRepository(client).transition(
            order_id,
            OrderStatus.REJECTED,
            1,
            1001,
            "primary",
            "review-6",
            {"reason": "payment mismatch"},
            uuid4(),
        )


@pytest.mark.asyncio
async def test_rejects_rpc_errors_without_exposing_transport_details() -> None:
    client = FakeClient(Response(None, error={"message": "database detail"}))

    with pytest.raises(AdminOrderReviewPersistenceError, match="database detail"):
        await SupabaseAdminOrderReviewRepository(client).transition(
            uuid4(),
            OrderStatus.APPROVED,
            1,
            1001,
            "primary",
            "review-7",
            None,
            uuid4(),
        )
