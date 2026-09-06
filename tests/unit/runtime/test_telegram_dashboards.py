from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.types import Update, User

from app.runtime.telegram.admin_dashboard import (
    ADMIN_FULFILLMENT_CALLBACK,
    ADMIN_IDENTITY_CALLBACK,
    ADMIN_ORDERS_CALLBACK,
    ADMIN_REVIEW_ORDERS_CALLBACK,
    admin_dashboard_markup,
    build_admin_dashboard_router,
    render_admin_dashboard,
)
from app.runtime.telegram.customer.dashboard import (
    DASHBOARD_BUY_CALLBACK,
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
        DASHBOARD_BUY_CALLBACK,
        DASHBOARD_ORDERS_CALLBACK,
    ]
    assert "لوحة المنارة" in render_customer_dashboard()


def test_admin_dashboard_only_exposes_orders_when_wired():
    assert [
        button.callback_data
        for row in admin_dashboard_markup().inline_keyboard
        for button in row
    ] == [ADMIN_IDENTITY_CALLBACK]
    assert [
        button.callback_data
        for row in admin_dashboard_markup(include_orders=True).inline_keyboard
        for button in row
    ] == [
        ADMIN_IDENTITY_CALLBACK,
        ADMIN_ORDERS_CALLBACK,
        ADMIN_REVIEW_ORDERS_CALLBACK,
        ADMIN_FULFILLMENT_CALLBACK,
    ]
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