from datetime import datetime, timezone
from decimal import Decimal
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Update, User

import app.runtime.telegram.bot_runtime as bot_runtime
from app.application.customer_order_listing import CustomerOrderListItem, CustomerOrderPage
from app.domain.order_status import OrderStatus
from app.runtime.telegram.bot_runtime import (
    POLLING_UPDATE_TYPES,
    SinglePollerLock,
    SharedPollerLeaseUnavailable,
    TelegramBotSettings,
)
from app.runtime.telegram.customer.orders import (
    ORDER_LISTING_RETRY_MESSAGE,
    parse_order_page_callback,
    render_order_page,
)
from app.runtime.telegram.customer_order_listing import (
    TelegramCustomerOrderListingInput,
    TelegramCustomerOrderListingResponse,
)
from app.runtime.telegram.router import build_customer_router, render_command_help
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id


def test_settings_reject_missing_runtime_secrets():
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        TelegramBotSettings.from_environment({})


def test_settings_reads_required_runtime_secrets():
    settings = TelegramBotSettings.from_environment(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        }
    )

    assert settings.token == "token"


def test_second_process_cannot_acquire_the_same_poller_lock(tmp_path: Path):
    first = SinglePollerLock(tmp_path / "telegram.lock")
    second = SinglePollerLock(tmp_path / "telegram.lock")

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()
    assert second.acquire() is True
    second.release()


def test_run_polling_clears_webhook_checks_identity_and_closes_session(monkeypatch):
    calls: list[object] = []

    class Session:
        async def close(self):
            calls.append("close")

    class Bot:
        session = Session()

        async def delete_webhook(self, *, drop_pending_updates):
            calls.append(("delete_webhook", drop_pending_updates))

        async def get_me(self):
            calls.append("get_me")
            return type("BotIdentity", (), {"id": 123})()

        async def set_my_commands(self, commands):
            calls.append(("set_my_commands", commands))

    class Dispatcher:
        async def start_polling(self, bot, **kwargs):
            calls.append(("start_polling", bot, kwargs))

    class Lease:
        async def acquire(self):
            return True

        async def renew(self):
            return True

        async def release(self):
            calls.append("release")
            return True

    monkeypatch.setattr(bot_runtime, "build_telegram_runtime", lambda _: (Bot(), Dispatcher()))
    asyncio.run(
        bot_runtime.run_polling(
            TelegramBotSettings("token", "url", "key"), Lease()
        )
    )

    assert calls[0] == ("delete_webhook", False)
    assert calls[1] == "get_me"
    assert calls[2][0] == "set_my_commands"
    assert calls[3][2] == {"allowed_updates": POLLING_UPDATE_TYPES}
    assert calls[4] == "close"
    assert calls[5] == "release"


def test_shared_lease_contention_fails_before_polling_starts(monkeypatch):
    class Lease:
        async def acquire(self):
            return False

        async def renew(self):
            raise AssertionError("renewal must not run")

        async def release(self):
            raise AssertionError("release must not run")

    monkeypatch.setattr(
        bot_runtime,
        "build_telegram_runtime",
        lambda _: pytest.fail("Telegram transport must not start without the lease"),
    )

    with pytest.raises(SharedPollerLeaseUnavailable):
        asyncio.run(
            bot_runtime.run_polling(TelegramBotSettings("token", "url", "key"), Lease())
        )


def test_lease_loss_stops_polling_and_releases_ownership(monkeypatch):
    calls: list[object] = []

    class Session:
        async def close(self):
            calls.append("close")

    class Bot:
        session = Session()

        async def delete_webhook(self, **_kwargs):
            calls.append("delete_webhook")

        async def get_me(self):
            return type("BotIdentity", (), {"id": 123})()

        async def set_my_commands(self, _commands):
            return None

    class Dispatcher:
        stopped = False

        async def start_polling(self, _bot, **_kwargs):
            while not self.stopped:
                await asyncio.sleep(0)
            calls.append("polling_stopped")

        async def stop_polling(self):
            self.stopped = True
            calls.append("stop_polling")

    class Lease:
        async def acquire(self):
            calls.append("acquire")
            return True

        async def renew(self):
            calls.append("renew")
            return False

        async def release(self):
            calls.append("release")
            return True

    monkeypatch.setattr(bot_runtime, "build_telegram_runtime", lambda _: (Bot(), Dispatcher()))
    asyncio.run(
        bot_runtime.run_polling(
            TelegramBotSettings("token", "url", "key"),
            Lease(),
            renewal_interval_seconds=0.001,
        )
    )

    assert calls == [
        "acquire",
        "delete_webhook",
        "renew",
        "stop_polling",
        "polling_stopped",
        "close",
        "release",
    ]


def test_timed_out_lease_renewal_stops_polling_before_expiry(monkeypatch):
    calls: list[str] = []

    class Session:
        async def close(self):
            calls.append("close")

    class Bot:
        session = Session()

        async def delete_webhook(self, **_kwargs):
            return None

        async def get_me(self):
            return type("BotIdentity", (), {"id": 123})()

        async def set_my_commands(self, _commands):
            return None

    class Dispatcher:
        stopped = False

        async def start_polling(self, _bot, **_kwargs):
            while not self.stopped:
                await asyncio.sleep(0)

        async def stop_polling(self):
            self.stopped = True
            calls.append("stop_polling")

    class Lease:
        async def acquire(self):
            return True

        async def renew(self):
            await asyncio.Event().wait()
            return True

        async def release(self):
            calls.append("release")
            return True

    monkeypatch.setattr(bot_runtime, "build_telegram_runtime", lambda _: (Bot(), Dispatcher()))
    asyncio.run(
        bot_runtime.run_polling(
            TelegramBotSettings("token", "url", "key"),
            Lease(),
            renewal_interval_seconds=0.001,
            renewal_timeout_seconds=0.001,
        )
    )

    assert calls == ["stop_polling", "close", "release"]


def test_runtime_build_failure_releases_acquired_shared_lease(monkeypatch):
    calls: list[str] = []

    class Lease:
        async def acquire(self):
            calls.append("acquire")
            return True

        async def renew(self):
            return True

        async def release(self):
            calls.append("release")
            return True

    monkeypatch.setattr(
        bot_runtime,
        "build_telegram_runtime",
        lambda _: (_ for _ in ()).throw(RuntimeError("runtime failed")),
    )

    with pytest.raises(RuntimeError, match="runtime failed"):
        asyncio.run(
            bot_runtime.run_polling(TelegramBotSettings("token", "url", "key"), Lease())
        )

    assert calls == ["acquire", "release"]


def test_main_refuses_to_start_a_second_poller():
    class LockedPoller:
        def __init__(self):
            self.released = False

        def acquire(self):
            return False

        def release(self):
            self.released = True

    lock = LockedPoller()
    with pytest.raises(SystemExit, match="1"):
        bot_runtime.main(lock=lock)

    assert lock.released is False


def test_main_runs_only_approved_update_types_and_releases_lock(monkeypatch):
    events: list[object] = []

    class Lock:
        def acquire(self):
            events.append("acquire")
            return True

        def release(self):
            events.append("release")

    settings = TelegramBotSettings("token", "https://example.supabase.co", "service-key")
    monkeypatch.setattr(TelegramBotSettings, "from_environment", lambda: settings)
    monkeypatch.setattr(bot_runtime.asyncio, "run", lambda coroutine: (coroutine.close(), events.append("run_polling")))

    bot_runtime.main(lock=Lock())

    assert events == [
        "acquire",
        "run_polling",
        "release",
    ]


@pytest.mark.parametrize(
    ("callback_data", "expected"),
    [
        ("orders:page:0", 0),
        ("orders:page:999", 999),
        ("orders:page:-1", None),
        ("orders:page:1:123", None),
        ("orders:page:1:customer:123", None),
        (None, None),
    ],
)
def test_callback_data_can_only_select_a_bounded_page(callback_data, expected):
    assert parse_order_page_callback(callback_data) == expected


def test_authenticated_identity_comes_from_update_user_not_callback_data():
    class User:
        id = 321

    class CallbackStub:
        from_user = User()
        data = "orders:page:2:customer:999"

    assert authenticated_telegram_user_id(CallbackStub()) == 321

@pytest.mark.parametrize(
    ("callback_data", "expected_action"),
    [
        ("identity:approve:00000000-0000-0000-0000-000000000001", "approve"),
        ("identity:reject:00000000-0000-0000-0000-000000000001", "reject"),
        ("identity:approve:00000000-0000-0000-0000-000000000001:primary", None),
        ("identity:approve:not-a-uuid", None),
    ],
)
def test_identity_review_callback_contains_only_action_and_submission_id(callback_data, expected_action):
    parsed = parse_identity_review_callback(callback_data)

    assert (parsed[0] if parsed else None) == expected_action
def test_update_errors_are_logged_without_the_exception_contents(caplog):
    secret_sentinel = "do-not-log-this-service-role-key"
    event = type("ErrorEventStub", (), {"exception": RuntimeError(secret_sentinel)})()

    assert asyncio.run(bot_runtime.log_telegram_error(event)) is True

    assert "Unhandled Telegram update error." in caplog.text
    assert secret_sentinel not in caplog.text


def test_command_help_explains_the_available_customer_action():
    help_text = render_command_help()

    assert "/orders" in help_text
    assert "المنارة" in help_text


def test_order_page_renders_customer_safe_summary_only():
    page = CustomerOrderPage(
        items=(
            CustomerOrderListItem(
                public_order_code="ORD-123",
                status=OrderStatus.PENDING_PAYMENT,
                version=1,
                network_code="BEP20",
                requested_amount=Decimal("10"),
                payment_currency="USD",
                local_amount=Decimal("10"),
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ),
        page=0,
        page_size=5,
        total_count=6,
    )

    text, markup = render_order_page(page)

    assert "ORD-123" in text
    assert "PENDING_PAYMENT" in text
    assert "wallet" not in text.lower()
    assert "internal" not in text.lower()
    assert markup.inline_keyboard[0][0].callback_data == "orders:page:1"


def _customer_order_page() -> CustomerOrderPage:
    return CustomerOrderPage(items=(), page=0, page_size=5, total_count=0)


async def _feed_customer_update(
    monkeypatch,
    composition: SimpleNamespace,
    update_data: dict[str, object],
) -> list[object]:
    sent_methods: list[object] = []

    async def capture_bot_request(_bot, method, **_kwargs):
        sent_methods.append(method)
        return True

    monkeypatch.setattr(bot_runtime.Bot, "__call__", capture_bot_request)
    bot = bot_runtime.Bot(token="123456:router-test-token")
    bot._me = User(id=123456, is_bot=True, first_name="Orders", username="OrdersBot")
    dispatcher = bot_runtime.Dispatcher()
    dispatcher.include_router(build_customer_router(composition))
    update = Update.model_validate(update_data, context={"bot": bot})
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    return sent_methods

async def _feed_identity_review_update(monkeypatch, handler, update_data: dict[str, object]) -> list[object]:
    sent_methods: list[object] = []

    async def capture_bot_request(_bot, method, **_kwargs):
        sent_methods.append(method)
        return True

    monkeypatch.setattr(bot_runtime.Bot, "__call__", capture_bot_request)
    bot = bot_runtime.Bot(token="123456:router-test-token")
    bot._me = User(id=123456, is_bot=True, first_name="Reviews", username="ReviewsBot")
    dispatcher = bot_runtime.Dispatcher()
    dispatcher.include_router(bot_runtime.build_identity_review_router(handler))
    update = Update.model_validate(update_data, context={"bot": bot})
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    return sent_methods
def _message_update(*, update_id: int, text: str, user_id: int) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Customer"},
            "text": text,
        },
    }


def test_router_dispatches_start_and_orders_through_aiogram(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=True, page=_customer_order_page()
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))

    start_methods = asyncio.run(
        _feed_customer_update(
            monkeypatch,
            composition,
            _message_update(update_id=1, text="/start", user_id=123),
        )
    )
    order_methods = asyncio.run(
        _feed_customer_update(
            monkeypatch,
            composition,
            _message_update(update_id=2, text="/orders", user_id=123),
        )
    )

    assert start_methods[0].text == render_command_help()
    assert order_methods[0].text == "لا توجد طلبات في هذه الصفحة."
    handle.assert_awaited_once_with(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=123,
            page=0,
            page_size=5,
        )
    )

def test_identity_review_is_private_and_uses_authenticated_callback_sender(monkeypatch):
    submission_id = "00000000-0000-0000-0000-000000000001"
    handler = SimpleNamespace(
        list_pending=AsyncMock(
            return_value=SimpleNamespace(ok=True, submissions=(), message="تم تحميل طلبات التحقق.")
        ),
        approve=AsyncMock(
            side_effect=[
                SimpleNamespace(ok=True, message="تم اعتماد بيانات العميل."),
                SimpleNamespace(ok=False, message="تعذر تحديث طلب التحقق حاليًا. حاول مجددًا."),
            ]
        ),
    )
    group_update = _message_update(update_id=30, text="/identity_pending", user_id=321)
    group_update["message"]["chat"] = {"id": -1001, "type": "group", "title": "Unsafe"}  # type: ignore[index]
    group_methods = asyncio.run(_feed_identity_review_update(monkeypatch, handler, group_update))

    callback_update = {
        "update_id": 31,
        "callback_query": {
            "id": "identity-approve-1",
            "from": {"id": 321, "is_bot": False, "first_name": "Primary"},
            "chat_instance": "admin-chat",
            "data": f"identity:approve:{submission_id}",
            "message": _message_update(update_id=32, text="pending", user_id=321)["message"],
        },
    }
    callback_methods = asyncio.run(
        _feed_identity_review_update(monkeypatch, handler, callback_update)
    )
    second_callback = dict(callback_update)
    second_callback["update_id"] = 33
    second_callback["callback_query"] = dict(callback_update["callback_query"])
    second_callback["callback_query"]["id"] = "identity-approve-2"
    second_methods = asyncio.run(
        _feed_identity_review_update(monkeypatch, handler, second_callback)
    )

    assert "محادثتك الخاصة" in group_methods[0].text
    handler.list_pending.assert_not_awaited()
    assert handler.approve.await_args_list[0].args[0] == 321
    assert str(handler.approve.await_args_list[0].args[1]) == submission_id
    assert callback_methods[0].callback_query_id == "identity-approve-1"
    assert callback_methods[1].reply_markup is None
    assert second_methods[0].text
def test_router_dispatches_addressed_group_orders_without_command_help(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=True, page=_customer_order_page()
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    group_orders_update = {
        "update_id": 7,
        "message": {
            "message_id": 7,
            "date": 0,
            "chat": {"id": -100987654321, "type": "supergroup", "title": "Customers"},
            "from": {"id": 456, "is_bot": False, "first_name": "Customer"},
            "text": "/orders@OrdersBot",
            "entities": [{"type": "bot_command", "offset": 0, "length": 17}],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, group_orders_update)
    )

    assert sent_methods[0].text == "لا توجد طلبات في هذه الصفحة."
    assert sent_methods[0].text != render_command_help()
    handle.assert_awaited_once_with(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=456,
            page=0,
            page_size=5,
        )
    )


def test_router_sends_order_listing_error_for_orders_command(monkeypatch):
    error_message = "Orders could not be loaded. Please retry."
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message=error_message
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))

    sent_methods = asyncio.run(
        _feed_customer_update(
            monkeypatch,
            composition,
            _message_update(update_id=8, text="/orders", user_id=123),
        )
    )

    assert sent_methods[0].text == error_message
    handle.assert_awaited_once_with(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=123,
            page=0,
            page_size=5,
        )
    )


def test_router_sends_retry_guidance_for_blank_order_listing_error(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message=" \t\n "
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))

    sent_methods = asyncio.run(
        _feed_customer_update(
            monkeypatch,
            composition,
            _message_update(update_id=11, text="/orders", user_id=123),
        )
    )

    assert sent_methods[0].text == ORDER_LISTING_RETRY_MESSAGE


def test_router_sends_retry_guidance_for_missing_order_listing_error(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message=None  # type: ignore[arg-type]
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))

    sent_methods = asyncio.run(
        _feed_customer_update(
            monkeypatch,
            composition,
            _message_update(update_id=14, text="/orders", user_id=123),
        )
    )

    assert sent_methods[0].text == ORDER_LISTING_RETRY_MESSAGE


def test_router_uses_callback_sender_identity_for_order_page(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=True, page=_customer_order_page()
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    callback_update = {
        "update_id": 3,
        "callback_query": {
            "id": "order-page-3",
            "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
            "chat_instance": "customer-chat",
            "data": "orders:page:2",
            "message": _message_update(update_id=4, text="/orders", user_id=321)[
                "message"
            ],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, callback_update)
    )

    assert sent_methods[0].callback_query_id == "order-page-3"
    assert sent_methods[1].text == "لا توجد طلبات في هذه الصفحة."
    handle.assert_awaited_once_with(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=321,
            page=2,
            page_size=5,
        )
    )


def test_router_acknowledges_and_renders_order_listing_error_for_page(monkeypatch):
    error_message = "Orders could not be loaded. Please retry."
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message=error_message
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    callback_update = {
        "update_id": 9,
        "callback_query": {
            "id": "order-page-error",
            "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
            "chat_instance": "customer-chat",
            "data": "orders:page:2",
            "message": _message_update(update_id=10, text="/orders", user_id=321)[
                "message"
            ],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, callback_update)
    )

    assert sent_methods[0].callback_query_id == "order-page-error"
    assert sent_methods[1].text == error_message
    handle.assert_awaited_once_with(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=321,
            page=2,
            page_size=5,
        )
    )


def test_router_edits_retry_guidance_for_blank_order_listing_page_error(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message="\n  "
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    callback_update = {
        "update_id": 12,
        "callback_query": {
            "id": "order-page-blank-error",
            "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
            "chat_instance": "customer-chat",
            "data": "orders:page:2",
            "message": _message_update(update_id=13, text="/orders", user_id=321)[
                "message"
            ],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, callback_update)
    )

    assert sent_methods[0].callback_query_id == "order-page-blank-error"
    assert sent_methods[1].text == ORDER_LISTING_RETRY_MESSAGE


def test_router_edits_retry_guidance_for_missing_order_listing_page_error(monkeypatch):
    handle = AsyncMock(
        return_value=TelegramCustomerOrderListingResponse(
            ok=False, message=None  # type: ignore[arg-type]
        )
    )
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    callback_update = {
        "update_id": 15,
        "callback_query": {
            "id": "order-page-missing-error",
            "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
            "chat_instance": "customer-chat",
            "data": "orders:page:2",
            "message": _message_update(update_id=16, text="/orders", user_id=321)["message"],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, callback_update)
    )

    assert sent_methods[0].callback_query_id == "order-page-missing-error"
    assert sent_methods[1].text == ORDER_LISTING_RETRY_MESSAGE


@pytest.mark.parametrize(
    "callback_data",
    ("orders:page:-1", "orders:page:1:customer:999", "not-an-order-page"),
)
def test_router_ignores_malformed_order_page_callbacks(monkeypatch, callback_data):
    handle = AsyncMock()
    composition = SimpleNamespace(order_listing=SimpleNamespace(handle=handle))
    callback_update = {
        "update_id": 5,
        "callback_query": {
            "id": "malformed-page",
            "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
            "chat_instance": "customer-chat",
            "data": callback_data,
            "message": _message_update(update_id=6, text="/orders", user_id=321)[
                "message"
            ],
        },
    }

    sent_methods = asyncio.run(
        _feed_customer_update(monkeypatch, composition, callback_update)
    )

    assert sent_methods == []
    handle.assert_not_awaited()
