from __future__ import annotations

import re
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.application.admin_order_review_details import (
    AdminOrderReviewDetailsService,
    GetAdminOrderReviewDetailsCommand,
)
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler

DETAILS_CALLBACK = re.compile(r"^admin:order:details:([0-9a-fA-F-]{36})$")
RECEIPT_CALLBACK = re.compile(r"^admin:order:receipt:([0-9a-fA-F-]{36})$")


def build_admin_order_review_details_router(
    service: AdminOrderReviewDetailsService,
    actor_type_resolver: object,
    session_handler: TelegramAdminSessionHandler,
) -> Router:
    router = Router(name="admin-order-review-details")

    async def resolve_details(admin_user_id: int, order_id: UUID):
        actor_type = await actor_type_resolver.resolve_actor_type(admin_user_id)
        if actor_type not in {"primary", "backup"}:
            raise PermissionError("admin is not authorized")
        session_response = await session_handler.create(admin_user_id, actor_type)
        if not session_response.ok or session_response.session is None:
            raise PermissionError("fresh admin session required")
        return await service.get(GetAdminOrderReviewDetailsCommand(
            admin_user_id, actor_type, order_id, session_response.session.session_id
        ))

    @router.callback_query(F.data.regexp(DETAILS_CALLBACK.pattern))
    async def open_details(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("مراجعة الطلبات متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        match = DETAILS_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("بيانات الطلب غير صالحة.", show_alert=True)
            return
        try:
            details = await resolve_details(admin_user_id, UUID(match.group(1)))
        except PermissionError:
            await query.answer("غير مصرح لك.", show_alert=True)
            return
        except LookupError:
            await query.answer("الطلب غير موجود أو لم يعد قيد المراجعة.", show_alert=True)
            return
        except Exception:
            await query.answer("تعذر تحميل تفاصيل الطلب.", show_alert=True)
            return

        lines = [
            f"🔎 {details.public_order_code}",
            f"الحالة: {details.status}",
            f"الإصدار: {details.version}",
            f"العميل: {details.user_telegram_id}",
            f"الشبكة: {details.network_code}",
            f"المبلغ المطلوب: {details.requested_amount} USDT",
            f"العملة: {details.payment_currency}",
            f"المبلغ المحلي المطلوب: {details.local_amount} {details.payment_currency}",
        ]
        markup = None
        if details.receipt_submission_id is None:
            lines.append("الإيصال: لا يوجد إيصال مسجل.")
        else:
            lines.extend([
                f"الإيصال: محاولة {details.receipt_attempt_number}",
                f"حالة الإيصال: {details.receipt_processing_status}",
                f"حالة الربط: {details.receipt_linkage_status}",
            ])
            if details.receipt_telegram_file_id:
                markup = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🧾 عرض الإيصال",
                        callback_data=f"admin:order:receipt:{details.internal_order_id}",
                    )
                ]])
        await query.answer()
        await query.message.answer("\n".join(lines), reply_markup=markup)

    @router.callback_query(F.data.regexp(RECEIPT_CALLBACK.pattern))
    async def show_receipt(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("عرض الإيصال متاح في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        match = RECEIPT_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("بيانات الإيصال غير صالحة.", show_alert=True)
            return
        try:
            details = await resolve_details(admin_user_id, UUID(match.group(1)))
            receipt = details.latest_receipt
            if receipt is None or not receipt.telegram_file_id:
                await query.answer("لا يوجد إيصال صورة متاح للعرض.", show_alert=True)
                return
            if receipt.input_type != "IMAGE" or receipt.mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                await query.answer("نوع الإيصال غير مسموح للعرض.", show_alert=True)
                return
            await query.answer()
            await query.message.answer_photo(
                receipt.telegram_file_id,
                caption=(
                    f"{details.public_order_code} — إيصال العميل، المحاولة {receipt.attempt_number}\n"
                    f"المبلغ المطلوب: {details.requested_amount} USDT\n"
                    f"المبلغ المحلي المطلوب: {details.local_amount} {details.payment_currency}"
                ),
            )
        except PermissionError:
            await query.answer("غير مصرح لك.", show_alert=True)
        except LookupError:
            await query.answer("الطلب غير موجود أو لم يعد قيد المراجعة.", show_alert=True)
        except Exception:
            await query.answer("تعذر عرض الإيصال.", show_alert=True)

    return router


def receipt_callback_data(order_id: UUID) -> str:
    return f"admin:order:details:{order_id}"
