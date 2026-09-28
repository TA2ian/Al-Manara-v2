from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from uuid import UUID

from app.runtime.telegram.admin_receipt_settings import TelegramAdminReceiptSettingsHandler
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message


CALLBACK_PREFIX = "admin:receipt_window:"
SHOW_CALLBACK = "admin:receipt_window"
PRESETS = (30, 60, 90)


def receipt_window_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{minutes} دقيقة", callback_data=f"{CALLBACK_PREFIX}{minutes}") for minutes in PRESETS]
    ])


def confirm_receipt_window_markup(confirmation_id: UUID, minutes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"تأكيد {minutes} دقيقة", callback_data=f"{CALLBACK_PREFIX}confirm:{confirmation_id}:{minutes}")],
        [InlineKeyboardButton(text="إلغاء", callback_data=f"{CALLBACK_PREFIX}cancel")],
    ])


def build_admin_receipt_settings_router(
    handler: TelegramAdminReceiptSettingsHandler,
    session_handler: TelegramAdminSessionHandler,
    actor_type_resolver,
) -> Router:
    router = Router(name="admin-receipt-settings")

    async def actor(user_id: int) -> str | None:
        try:
            value = await actor_type_resolver.resolve_actor_type(user_id)
        except Exception:
            return None
        return value if value in {"primary", "backup"} else None

    async def show(message: Message) -> None:
        if not is_private_message(message):
            await message.answer("إعدادات الإدارة متاحة في المحادثة الخاصة فقط.")
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        actor_value = await actor(user_id)
        if actor_value is None:
            await message.answer("غير مصرح لك.")
            return
        current = await handler.get()
        if not current.ok or current.setting is None:
            await message.answer(current.message or "تعذر تحميل مهلة الإيصال.")
            return
        await message.answer(
            f"مهلة إرسال إيصال ShamCash الحالية: {current.setting.minutes} دقيقة.\n"
            "يمكن للأدمن ضبطها من 1 إلى 90 دقيقة. الافتراضي 60 دقيقة؛ اختيار قيمة فوق 60 دقيقة هو تمديد صريح.",
            reply_markup=receipt_window_markup(),
        )

    @router.message(Command("receipt_window"))
    async def receipt_window_command(message: Message) -> None:
        parts = (message.text or "").split()
        if len(parts) == 1:
            await show(message)
            return
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("استخدم: /receipt_window 60")
            return
        await request(message, int(parts[1]))

    async def request(message: Message, minutes: int) -> None:
        if not is_private_message(message):
            await message.answer("إعدادات الإدارة متاحة في المحادثة الخاصة فقط.")
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        actor_value = await actor(user_id)
        if actor_value is None:
            await message.answer("غير مصرح لك.")
            return
        session = await session_handler.create(user_id, actor_value)
        if not session.ok or session.session is None:
            await message.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.")
            return
        response = await handler.request_update(user_id, actor_value, session.session.session_id, minutes)
        if not response.ok or response.confirmation_id is None:
            await message.answer(response.message or "تعذر تجهيز التغيير.")
            return
        await message.answer(
            f"طلب تغيير مهلة الإيصال إلى {minutes} دقيقة جاهز. صلاحية التأكيد قصيرة ويجب تأكيد العملية الآن.",
            reply_markup=confirm_receipt_window_markup(response.confirmation_id, minutes),
        )

    @router.callback_query(F.data == SHOW_CALLBACK)
    async def settings_callback(query: CallbackQuery) -> None:
        if query.message is None:
            await query.answer("بيانات الطلب غير متاحة.", show_alert=True)
            return
        await query.answer()
        await show(query.message)

    @router.callback_query(F.data.regexp(r"^admin:receipt_window:(?:[0-9]+)$"))
    async def preset_callback(query: CallbackQuery) -> None:
        if query.message is None:
            await query.answer("بيانات الطلب غير متاحة.", show_alert=True)
            return
        try:
            minutes = int((query.data or "").rsplit(":", 1)[1])
        except (ValueError, IndexError):
            await query.answer("قيمة غير صالحة.", show_alert=True)
            return
        await query.answer()
        await request(query.message, minutes)

    @router.callback_query(F.data.regexp(r"^admin:receipt_window:confirm:[0-9a-fA-F-]{36}:[0-9]+$"))
    async def confirm_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("إعدادات الإدارة متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        actor_value = await actor(user_id)
        if actor_value is None:
            await query.answer("غير مصرح لك.", show_alert=True)
            return
        try:
            _, _, _, confirmation_text, minutes_text = (query.data or "").split(":")
            confirmation_id = UUID(confirmation_text)
            minutes = int(minutes_text)
        except (ValueError, TypeError):
            await query.answer("بيانات التأكيد غير صالحة.", show_alert=True)
            return
        response = await handler.confirm_update(user_id, actor_value, confirmation_id, minutes)
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok and response.setting is not None:
            await query.message.edit_text(
                f"تم تحديث مهلة إرسال الإيصال إلى {response.setting.minutes} دقيقة.",
                reply_markup=receipt_window_markup(),
            )

    @router.callback_query(F.data == f"{CALLBACK_PREFIX}cancel")
    async def cancel_callback(query: CallbackQuery) -> None:
        await query.answer("تم إلغاء التغيير.")
        if query.message is not None:
            await query.message.edit_text("تم إلغاء تغيير مهلة الإيصال.", reply_markup=receipt_window_markup())

    return router
