from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.admin_customer_identity import TelegramAdminCustomerIdentityHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

IDENTITY_REVIEW_CALLBACK = re.compile(r"identity:(approve|reject):([0-9a-fA-F-]{36})")
IDENTITY_REVIEW_PAGE_LIMIT = 20


class IdentityReviewState(StatesGroup):
    rejection_reason = State()


def parse_identity_review_callback(callback_data: str | None) -> tuple[str, UUID] | None:
    match = IDENTITY_REVIEW_CALLBACK.fullmatch(callback_data or "")
    if match is None:
        return None
    try:
        return match.group(1), UUID(match.group(2))
    except ValueError:
        return None


def _identity_review_markup(submission_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="اعتماد", callback_data=f"identity:approve:{submission_id}"
                ),
                InlineKeyboardButton(
                    text="رفض", callback_data=f"identity:reject:{submission_id}"
                ),
            ]
        ]
    )


def _identity_review_caption(submission: Any) -> str:
    return (
        "طلب تحقق بانتظار المراجعة\n"
        f"العميل: {submission.customer_telegram_user_id}\n"
        f"الاسم: {submission.full_name}\n"
        f"حساب Sham Cash: {submission.shamcash_account}\n"
        f"قُدّم: {submission.submitted_at.isoformat()}"
    )


def build_identity_review_router(handler: TelegramAdminCustomerIdentityHandler) -> Router:
    """Routes primary-admin identity review through private Telegram chats only."""
    router = Router(name="primary-admin-customer-identity")

    @router.message(Command("identity_pending"))
    async def show_pending_identity_submissions(message: Message) -> None:
        if not is_private_message(message):
            await message.answer("مراجعة طلبات التحقق متاحة في المحادثة الخاصة فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        response = await handler.list_pending(admin_user_id)
        if not response.ok:
            await message.answer(response.message or "تعذر تحميل طلبات التحقق.")
            return
        if not response.submissions:
            await message.answer("لا توجد طلبات تحقق معلقة.")
            return
        await message.answer("طلبات التحقق المعلقة:")
        for submission in response.submissions[:IDENTITY_REVIEW_PAGE_LIMIT]:
            try:
                await message.answer_photo(
                    submission.qr_image_file_id,
                    caption=_identity_review_caption(submission),
                    reply_markup=_identity_review_markup(submission.submission_id),
                )
            except Exception:
                await message.answer("تعذر عرض صورة QR لأحد الطلبات. حاول لاحقًا.")
        if len(response.submissions) > IDENTITY_REVIEW_PAGE_LIMIT:
            await message.answer("توجد طلبات إضافية. راجع هذه الدفعة أولًا ثم أعد الأمر.")

    @router.callback_query(F.data.regexp(IDENTITY_REVIEW_CALLBACK.pattern))
    async def review_identity_submission(query: CallbackQuery, state: FSMContext) -> None:
        parsed = parse_identity_review_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if query.message is None or getattr(query.message.chat, "type", None) != "private":
            await query.answer("المراجعة متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        action, submission_id = parsed
        if action == "reject":
            await state.clear()
            await state.update_data(identity_submission_id=str(submission_id))
            await state.set_state(IdentityReviewState.rejection_reason)
            await query.answer()
            await query.message.answer("أرسل سبب الرفض (من 1 إلى 500 حرف).")
            return
        response = await handler.approve(admin_user_id, submission_id)
        await query.answer(
            response.message or "تعذر تحديث طلب التحقق.", show_alert=not response.ok
        )
        if response.ok:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.message(IdentityReviewState.rejection_reason, F.text)
    async def receive_identity_rejection_reason(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إرسال سبب الرفض متاح في المحادثة الخاصة فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await state.clear()
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        values = await state.get_data()
        try:
            submission_id = UUID(str(values.get("identity_submission_id")))
        except (TypeError, ValueError):
            await state.clear()
            await message.answer("طلب التحقق غير صالح.")
            return
        response = await handler.reject(admin_user_id, submission_id, message.text or "")
        if response.ok:
            await state.clear()
        await message.answer(response.message or "تعذر تحديث طلب التحقق.")

    return router
