from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.admin_order_listing import TelegramAdminOrderListingHandler, TelegramAdminOrderListingInput
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

ADMIN_DASHBOARD_CALLBACK = "admin:dashboard"
ADMIN_IDENTITY_CALLBACK = "admin:identity_pending"
ADMIN_ORDERS_CALLBACK = "admin:orders"
ADMIN_ORDER_PAGE_SIZE = 5


def admin_dashboard_markup(*, include_orders: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👥 التحقق من المستخدمين", callback_data=ADMIN_IDENTITY_CALLBACK)]]
    if include_orders:
        rows.append([InlineKeyboardButton(text="📦 الطلبات النشطة", callback_data=ADMIN_ORDERS_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_admin_dashboard() -> str:
    return (
        "📊 لوحة تحكم الإدارة\n\n"
        "اختر إحدى العمليات المتاحة.\n"
        "تظهر العمليات هنا فقط بعد اجتياز صلاحيات الإدارة."
    )


def _render_orders(page) -> str:
    if not page.items:
        return "لا توجد طلبات نشطة حاليًا."
    lines = [f"📦 الطلبات النشطة ({page.total_count})", ""]
    for item in page.items:
        lines.append(
            f"• {item.public_order_code} | {item.status}\n"
            f"  العميل: {item.user_telegram_id}\n"
            f"  الشبكة: {item.network_code}"
        )
    if page.total_count > page.page_size:
        lines.append(f"\nالصفحة {page.page + 1}")
    return "\n".join(lines)


def build_admin_dashboard_router(handler, order_listing: TelegramAdminOrderListingHandler | None = None):
    router = Router(name="admin-dashboard")

    async def authorize(user_id: int):
        return await handler.list_pending(user_id)

    async def show_dashboard(message: Message) -> None:
        if not is_private_message(message):
            await message.answer("لوحة الإدارة متاحة في المحادثة الخاصة مع البوت فقط.")
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        authorization = await authorize(user_id)
        if not authorization.ok:
            await message.answer(authorization.message or "غير مصرح لك بالوصول إلى لوحة الإدارة.")
            return
        await message.answer(
            render_admin_dashboard(),
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.message(Command("admin"))
    async def admin_command(message: Message) -> None:
        await show_dashboard(message)

    @router.callback_query(F.data == ADMIN_DASHBOARD_CALLBACK)
    async def dashboard_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("لوحة الإدارة متاحة في المحادثة الخاصة مع البوت فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        authorization = await authorize(user_id)
        if not authorization.ok:
            await query.answer(authorization.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            render_admin_dashboard(),
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.callback_query(F.data == ADMIN_IDENTITY_CALLBACK)
    async def identity_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("مراجعة طلبات التحقق متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        response = await authorize(user_id)
        if not response.ok:
            await query.answer(response.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        if not response.submissions:
            await query.message.answer("لا توجد طلبات تحقق معلقة.")
            return
        await query.message.answer("للمراجعة التفصيلية أرسل /identity_pending.")

    if order_listing is not None:
        @router.callback_query(F.data == ADMIN_ORDERS_CALLBACK)
        async def orders_callback(query: CallbackQuery) -> None:
            if query.message is None or not is_private_message(query.message):
                await query.answer("عرض الطلبات متاح في المحادثة الخاصة فقط.", show_alert=True)
                return
            user_id = authenticated_telegram_user_id(query)
            if user_id is None:
                await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
                return
            authorization = await authorize(user_id)
            if not authorization.ok:
                await query.answer(authorization.message or "غير مصرح لك.", show_alert=True)
                return
            await query.answer()
            response = await order_listing.handle(
                TelegramAdminOrderListingInput(
                    admin_user_id=user_id,
                    actor_type="primary",
                    list_type="active",
                    page=0,
                    page_size=ADMIN_ORDER_PAGE_SIZE,
                )
            )
            if not response.ok or response.page is None:
                await query.message.answer(response.message or "تعذر تحميل الطلبات.")
                return
            await query.message.answer(_render_orders(response.page))

    return router
