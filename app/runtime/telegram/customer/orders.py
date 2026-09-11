from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.customer_order_listing import CustomerOrderPage
from app.composition_root import CustomerComposition
from app.runtime.telegram.customer_order_listing import (
    TelegramCustomerOrderListingInput,
    TelegramCustomerOrderListingResponse,
)
from app.runtime.telegram.messages import customer_safe_message
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

ORDER_PAGE_SIZE = 5
ORDER_PAGE_CALLBACK = re.compile(r"^orders:page:(\d{1,3})$")
ORDER_LISTING_RETRY_MESSAGE = "Orders could not be loaded. Please retry."
PRIVATE_CHAT_REQUIRED = "حفاظًا على خصوصيتك، اعرض طلباتك في محادثة خاصة مع البوت."


def parse_order_page_callback(callback_data: str | None) -> int | None:
    match = ORDER_PAGE_CALLBACK.fullmatch(callback_data or "")
    return int(match.group(1)) if match else None


def render_order_listing_failure(message: object | None) -> str:
    return customer_safe_message(message, ORDER_LISTING_RETRY_MESSAGE)


def render_order_page(page: CustomerOrderPage) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page.items:
        text = "لا توجد طلبات في هذه الصفحة."
    else:
        lines = ["طلباتك:"]
        for item in page.items:
            amount = (
                f"{item.local_amount} {item.payment_currency}"
                if item.local_amount is not None and item.payment_currency
                else "القيمة قيد التحديد"
            )
            lines.append(
                f"• {item.public_order_code}\n"
                f"  الحالة: {item.status.value} | الشبكة: {item.network_code}\n"
                f"  المبلغ: {amount}"
            )
        text = "\n".join(lines)

    buttons: list[InlineKeyboardButton] = []
    if page.page > 0:
        buttons.append(
            InlineKeyboardButton(text="السابق", callback_data=f"orders:page:{page.page - 1}")
        )
    if (page.page + 1) * page.page_size < page.total_count:
        buttons.append(
            InlineKeyboardButton(text="التالي", callback_data=f"orders:page:{page.page + 1}")
        )
    return text, InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None


async def _load_orders(
    update: Message | CallbackQuery, composition: CustomerComposition, page: int
) -> TelegramCustomerOrderListingResponse | None:
    if isinstance(update, Message):
        if not is_private_message(update):
            await update.answer(PRIVATE_CHAT_REQUIRED)
            return None
    elif update.message is not None and not is_private_message(update.message):
        await update.answer(PRIVATE_CHAT_REQUIRED, show_alert=True)
        return None
    user_id = authenticated_telegram_user_id(update)
    if user_id is None:
        return None
    return await composition.order_listing.handle(
        TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=user_id,
            page=page,
            page_size=ORDER_PAGE_SIZE,
        )
    )


def build_customer_orders_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer-orders")

    @router.message(Command("orders"))
    async def show_customer_orders(message: Message) -> None:
        response = await _load_orders(message, composition, page=0)
        if response is None:
            return
        if not response.ok or response.page is None:
            await message.answer(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await message.answer(text, reply_markup=markup)

    @router.callback_query(F.data.regexp(ORDER_PAGE_CALLBACK))
    async def show_customer_orders_page(query: CallbackQuery) -> None:
        page = parse_order_page_callback(query.data)
        if page is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        await query.answer()
        response = await _load_orders(query, composition, page=page)
        if response is None or query.message is None:
            return
        if not response.ok or response.page is None:
            await query.message.edit_text(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await query.message.edit_text(text, reply_markup=markup)

    return router