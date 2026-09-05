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
from app.runtime.telegram.admin_identity_review import parse_identity_review_callback
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
