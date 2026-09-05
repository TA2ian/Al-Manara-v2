from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.types import Update, User

from app.runtime.telegram.admin_customer_identity import TelegramAdminCustomerIdentityHandler
from app.runtime.telegram.admin_dashboard import (
    ADMIN_IDENTITY_CALLBACK,
    admin_dashboard_markup,
    build_admin_dashboard_router,
    render_admin_dashboard,
)
from app.runtime.telegram.customer.dashboard import (
    DASHBOARD_ORDERS_CALLBACK,
    build_customer_dashboard_router,
    customer_dashboard_markup,
    render_customer_dashboard,
)


def test_customer_dashboard_has_only_real_current_actions():
    markup = customer_dashboard_markup()
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callbacks == [
        "customer:verify",
        "customer:wallets",
        DASHBOARD_ORDERS_CALLBACK,
    ]
    assert "لوحة المنارة" in render_customer_dashboard()


def test_admin_dashboard_is_explicitly_privileged():
    markup = admin_dashboard_markup()
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callbacks == [ADMIN_IDENTITY_CALLBACK]
    assert "لوحة تحكم الإدارة" in render_admin_dashboard()


def test_customer_dashboard_orders_uses_authenticated_sender(monkeypatch):
    handle = AsyncMock(
        return_value=SimpleNamespace(
            ok=True,
            page=SimpleNamespace(items=(), page=0, page_size=5, total_count=0),
        )
    )
    composition = SimpleNamespace(
        order_listing=SimpleNamespace(handle=handle),
        wallets=SimpleNamespace(list=AsyncMock()),
    )

    sent: list[object] = []

    async def capture(_bot, method, **_kwargs):
        sent.append(method)
        return True

    async def run():
        monkeypatch.setattr(Bot, "__call__", capture)
        bot = Bot(token="123456:dashboard-test-token")
        bot._me = User(id=123456, is_bot=True, first_name="Dashboard")
        dispatcher = Dispatcher()
        dispatcher.include_router(build_customer_dashboard_router(composition))
        update = Update.model_validate(
            {
                "update_id": 1,
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
                    "chat_instance": "chat-instance",
                    "data": DASHBOARD_ORDERS_CALLBACK,
                    "message": {
                        "message_id": 1,
                        "date": 0,
                        "chat": {"id": 321, "type": "private"},
                        "from": {"id": 321, "is_bot": False, "first_name": "Customer"},
                        "text": "لوحة المنارة",
                    },
                },
            },
            context={"bot": bot},
        )
        try:
            await dispatcher.feed_update(bot, update)
        finally:
            await bot.session.close()

    asyncio.run(run())

    assert handle.await_count == 1
    request = handle.await_args.args[0]
    assert request.authenticated_telegram_user_id == 321
    assert sent


def test_admin_dashboard_denies_non_admin_without_showing_dashboard():
    handler = SimpleNamespace(
        list_pending=AsyncMock(
            return_value=SimpleNamespace(ok=False, submissions=(), message="غير مصرح لك.")
        )
    )
    assert isinstance(build_admin_dashboard_router(handler), type(build_customer_dashboard_router(SimpleNamespace())))
    assert isinstance(handler, SimpleNamespace)
