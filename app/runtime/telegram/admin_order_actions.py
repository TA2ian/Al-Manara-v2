from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.admin_order_review import TelegramAdminOrderReviewHandler, TelegramAdminReviewInput
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

ORDER_ACTION_CALLBACK = re.compile(
    r"^admin:order:(approve|reject|clarify):([0-9a-fA-F-]{36}):(\d+)$"
)
MAX_REASON_LENGTH = 1000


class AdminOrderActionState(StatesGroup):
    reason = State()


@dataclass(frozen=True, slots=True)
class PendingOrderAction:
    action: str
    order_id: UUID
    expected_version: int


def parse_order_action_callback(data: str | None) -> PendingOrderAction | None:
    match = ORDER_ACTION_CALLBACK.fullmatch(data or "")
    if match is None:
        return None
    try:
        return PendingOrderAction(
            action=match.group(1),
            order_id=UUID(match.group(2)),
            expected_version=int(match.group(3)),
        )
    except ValueError:
        return None


def order_action_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="اعتماد",
                    callback_data=f"admin:order:approve:{order_id}:{expected_version}",
                ),
                InlineKeyboardButton(
                    text="رفض",
                    callback_data=f"admin:order:reject:{order_id}:{expected_version}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="طلب توضيح",
                    callback_data=f"admin:order:clarify:{order_id}:{expected_version}",
                )
            ],
        ]
    )


def build_admin_order_actions_router(handler: TelegramAdminOrderReviewHandler) -> Router:
    router = Router(name="admin-order-actions")

    @router.callback_query(F.data.regexp(ORDER_ACTION_CALLBACK.pattern))
    async def handle_order_action(query: CallbackQuery, state: FSMContext) -> None:
        action = parse_order_action_callback(query.data)
        if action is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة الطلبات متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return

        if action.action in {"reject", "clarify"}:
            await state.clear()
            await state.update_data(
                order_action=action.action,
                order_id=str(action.order_id),
                expected_version=action.expected_version,
            )
            await state.set_state(AdminOrderActionState.reason)
            await query.answer()
            await query.message.answer(
                "أرسل سبب الرفض أو طلب التوضيح (من 5 إلى 1000 حرف)."
            )
            return

        response = await handler.handle(
            TelegramAdminReviewInput(
                admin_user_id=admin_user_id,
                actor_type="primary",
                order_id=action.order_id,
                expected_version=action.expected_version,
                action=action.action,
                idempotency_key=str(uuid4()),
            )
        )
        await query.answer(response.message or "تعذر تحديث الطلب.", show_alert=not response.ok)
        if response.ok:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.message(AdminOrderActionState.reason, F.text)
    async def receive_order_reason(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إرسال السبب متاح في المحادثة الخاصة فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await state.clear()
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        reason = " ".join((message.text or "").split())
        if not 5 <= len(reason) <= MAX_REASON_LENGTH:
            await message.answer("السبب يجب أن يكون بين 5 و1000 حرف.")
            return
        values = await state.get_data()
        try:
            order_id = UUID(str(values["order_id"]))
            expected_version = int(values["expected_version"])
            action = str(values["order_action"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("بيانات عملية الطلب غير صالحة.")
            return

        response = await handler.handle(
            TelegramAdminReviewInput(
                admin_user_id=admin_user_id,
                actor_type="primary",
                order_id=order_id,
                expected_version=expected_version,
                action=action,
                reason=reason,
                idempotency_key=str(uuid4()),
            )
        )
        if response.ok:
            await state.clear()
        await message.answer(response.message or "تعذر تحديث الطلب.")

    return router
