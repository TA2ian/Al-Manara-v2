from uuid import UUID, uuid4

import pytest

from app.runtime.telegram.admin_order_actions import (
    AdminOrderActionState,
    _resolve_actor_type,
    order_action_markup,
    parse_order_action_callback,
)


def test_parse_order_action_callback_accepts_valid_payload() -> None:
    order_id = uuid4()
    parsed = parse_order_action_callback(f"admin:order:approve:{order_id}:7")

    assert parsed is not None
    assert parsed.action == "approve"
    assert parsed.order_id == order_id
    assert parsed.expected_version == 7


def test_parse_order_action_callback_rejects_malformed_payload() -> None:
    assert parse_order_action_callback("admin:order:approve:not-a-uuid:7") is None
    assert parse_order_action_callback("admin:order:approve:" + str(uuid4()) + ":0") is not None
    assert parse_order_action_callback("admin:order:delete:" + str(uuid4()) + ":7") is None


def test_order_action_markup_carries_internal_order_id_and_version() -> None:
    order_id = UUID("11111111-1111-1111-1111-111111111111")
    markup = order_action_markup(order_id, 9)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callbacks == [
        f"admin:order:approve:{order_id}:9",
        f"admin:order:reject:{order_id}:9",
        f"admin:order:clarify:{order_id}:9",
    ]


def test_reason_state_is_defined() -> None:
    assert AdminOrderActionState.reason.state == "AdminOrderActionState:reason"


class FakeActorResolver:
    def __init__(self, actor_type: str | None = "backup", error: Exception | None = None) -> None:
        self.actor_type = actor_type
        self.error = error
        self.calls: list[int] = []

    async def resolve_actor_type(self, telegram_user_id: int) -> str | None:
        self.calls.append(telegram_user_id)
        if self.error is not None:
            raise self.error
        return self.actor_type


@pytest.mark.asyncio
async def test_resolve_actor_type_uses_db_authority() -> None:
    resolver = FakeActorResolver("backup")

    result = await _resolve_actor_type(resolver, 123)

    assert result == "backup"
    assert resolver.calls == [123]


@pytest.mark.asyncio
async def test_resolve_actor_type_rejects_unknown_value() -> None:
    resolver = FakeActorResolver("primary;DROP")

    result = await _resolve_actor_type(resolver, 123)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_actor_type_fails_closed_on_resolution_error() -> None:
    resolver = FakeActorResolver(error=RuntimeError("db unavailable"))

    result = await _resolve_actor_type(resolver, 123)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_actor_type_fails_closed_without_resolver() -> None:
    assert await _resolve_actor_type(None, 123) is None
