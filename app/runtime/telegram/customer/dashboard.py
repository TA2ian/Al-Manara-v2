from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.composition_root import CustomerComposition
from app.runtime.telegram.customer.orders import ORDER_PAGE_SIZE, render_order_listing_failure, render_order_page
from app.runtime.telegram.customer_order_listing import TelegramCustomerOrderListingInput
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

DASHBOARD_CALLBACK = "customer:dashboard"
DASHBOARD_ORDERS_CALLBACK = "customer:orders"
DASHBOARD_WALLETS_CALLBACK = "customer:wallets"
DASHBOARD_VERIFY_CALLBACK = "customer:verify"
PRIVATE_DASHBOARD_MESSAGE = "لوحة العميل متاحة في المحادثة الخاصة مع البوت فقط."


def customer_dashboard_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🪪 التحقق من الهوية", callback_data=DASHBOARD_VERIFY_CALLBACK),
                InlineKeyboardButton(text="👛 محافظي", callback_data=DASHBOARD_WALLETS_CALLBACK),
            ],
            [InlineKeyboardButton(text="📦 طلباتي", callback_data=DASHBOARD_ORDERS_CALLBACK)],
        ]
    )


def render_customer_dashboard() -> str:
    return (
        "🏠 لوحة المنارة\n\n"
        "اختر الخدمة المطلوبة من القائمة أدناه.\n"
        "يمكنك أيضًا استخدام /verify و /orders مباشرة."
    )


def build_customer_dashboard_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer-dashboard")

    async def show_dashboard(message: Message) -> None:
        if not is_private_message(message):
            await message.answer(PRIVATE_DASHBOARD_MESSAGE)
            return
        await message.answer(render_customer_dashboard(), reply_markup=customer_dashboard_markup())

    @router.message(CommandStart())
    @router.message(F.text.startswith("/start "))
    async def start(message: Message) -> None:
        await show_dashboard(message)

    @router.callback_query(F.data == DASHBOARD_CALLBACK)
    async def dashboard_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer(PRIVATE_DASHBOARD_MESSAGE, show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            render_customer_dashboard(), reply_markup=customer_dashboard_markup()
        )

    @router.callback_query(F.data == DASHBOARD_VERIFY_CALLBACK)
    async def verify_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer(PRIVATE_DASHBOARD_MESSAGE, show_alert=True)
            return
        await query.answer()
        await query.message.answer("لبدء أو استكمال التحقق من الهوية، أرسل /verify.")

    @router.callback_query(F.data == DASHBOARD_WALLETS_CALLBACK)
    async def wallets_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer(PRIVATE_DASHBOARD_MESSAGE, show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المستخدم.", show_alert=True)
            return
        await query.answer()
        response = await composition.wallets.list(user_id)
        await query.message.answer(response.text)

    @router.callback_query(F.data == DASHBOARD_ORDERS_CALLBACK)
    async def orders_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer(PRIVATE_DASHBOARD_MESSAGE, show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المستخدم.", show_alert=True)
            return
        await query.answer()
        response = await composition.order_listing.handle(
            TelegramCustomerOrderListingInput(
                authenticated_telegram_user_id=user_id,
                page=0,
                page_size=ORDER_PAGE_SIZE,
            )
        )
        if not response.ok or response.page is None:
            await query.message.answer(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await query.message.answer(text, reply_markup=markup)

    return router
