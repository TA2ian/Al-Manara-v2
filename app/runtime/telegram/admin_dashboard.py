from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.composition_root import AdminComposition
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

ADMIN_DASHBOARD_CALLBACK = "admin:dashboard"
ADMIN_IDENTITY_CALLBACK = "admin:identity_pending"


def admin_dashboard_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 التحقق من المستخدمين", callback_data=ADMIN_IDENTITY_CALLBACK)],
        ]
    )


def render_admin_dashboard() -> str:
    return (
        "📊 لوحة تحكم الإدارة\n\n"
        "اختر إحدى العمليات المتاحة.\n"
        "تظهر العمليات هنا فقط بعد اجتياز صلاحيات الإدارة."
    )


def build_admin_dashboard_router(composition: AdminComposition) -> Router:
    router = Router(name="admin-dashboard")

    async def show_dashboard(message: Message) -> None:
        if not is_private_message(message):
            await message.answer("لوحة الإدارة متاحة في المحادثة الخاصة مع البوت فقط.")
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        authorization = await composition.identity_review.list_pending(user_id)
        if not authorization.ok:
            await message.answer(authorization.message or "غير مصرح لك بالوصول إلى لوحة الإدارة.")
            return
        await message.answer(render_admin_dashboard(), reply_markup=admin_dashboard_markup())

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
        authorization = await composition.identity_review.list_pending(user_id)
        if not authorization.ok:
            await query.answer(authorization.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(render_admin_dashboard(), reply_markup=admin_dashboard_markup())

    @router.callback_query(F.data == ADMIN_IDENTITY_CALLBACK)
    async def identity_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("مراجعة طلبات التحقق متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        response = await composition.identity_review.list_pending(user_id)
        if not response.ok:
            await query.answer(response.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        if not response.submissions:
            await query.message.answer("لا توجد طلبات تحقق معلقة.")
            return
        await query.message.answer("للمراجعة التفصيلية أرسل /identity_pending.")

    return router
