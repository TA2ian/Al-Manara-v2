from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.admin_order_review import AdminOrderReviewService
from app.runtime.telegram.admin_order_review import TelegramAdminOrderReviewHandler, TelegramAdminReviewInput
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

ORDER_ACTION_CALLBACK = re.compile(
    r"^admin:order:(approve|reject|clarify|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$"
)
MAX_REASON_LENGTH = 1000


class AdminOrderActionState(StatesGroup):
    reason = State()
    confirmation = State()


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


def _confirmation_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="تأكيد العملية",
                    callback_data=f"admin:order:confirm:{order_id}:{expected_version}",
                ),
                InlineKeyboardButton(
                    text="إلغاء",
                    callback_data=f"admin:order:cancel:{order_id}:{expected_version}",
                ),
            ]
        ]
    )


async def _resolve_actor_type(resolver: object | None, admin_user_id: int) -> str | None:
    if resolver is None:
        return None
    try:
        actor_type = await resolver.resolve_actor_type(admin_user_id)  # type: ignore[attr-defined]
    except Exception:
        return None
    return actor_type if actor_type in {"primary", "backup"} else None


def build_admin_order_actions_router(
    handler: TelegramAdminOrderReviewHandler,
    session_handler: TelegramAdminSessionHandler,
    actor_type_resolver: object | None = None,
) -> Router:
    router = Router(name="admin-order-actions")
    resolver = actor_type_resolver or getattr(handler, "_actor_type_resolver", None)

    @router.callback_query(F.data.regexp(ORDER_ACTION_CALLBACK.pattern))
    async def handle_order_action(query: CallbackQuery, state: FSMContext) -> None:
        parsed = parse_order_action_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة الطلبات متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        actor_type = await _resolve_actor_type(resolver, admin_user_id)
        if actor_type is None:
            await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
            return

        data = await state.get_data()
        pending_admin = data.get("admin_user_id")
        pending_order = data.get("order_id")
        pending_version = data.get("expected_version")

        if parsed.action in {"approve", "reject", "clarify"}:
            if parsed.action in {"reject", "clarify"}:
                await state.clear()
                await state.update_data(
                    admin_user_id=admin_user_id,
                    order_action=parsed.action,
                    order_id=str(parsed.order_id),
                    expected_version=parsed.expected_version,
                    actor_type=actor_type,
                )
                await state.set_state(AdminOrderActionState.reason)
                await query.answer()
                await query.message.answer("أرسل سبب الرفض أو طلب التوضيح (من 5 إلى 1000 حرف).")
                return

            session_response = await session_handler.create(admin_user_id, actor_type)
            if not session_response.ok or session_response.session is None:
                await query.answer(session_response.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
                return
            await state.clear()
            await state.update_data(
                admin_user_id=admin_user_id,
                order_action=parsed.action,
                order_id=str(parsed.order_id),
                expected_version=parsed.expected_version,
                actor_type=actor_type,
                session_id=str(session_response.session.session_id),
                idempotency_key=f"review:{uuid4().hex}",
            )
            try:
                session_id = UUID(str((await state.get_data())["session_id"]))
                values = await state.get_data()
                idempotency_key = str(values["idempotency_key"])
                fingerprint = AdminOrderReviewService.review_fingerprint(
                    parsed.order_id, parsed.expected_version, admin_user_id, actor_type,
                    parsed.action, None, idempotency_key
                )
                confirmation_id = await handler.create_confirmation(TelegramAdminReviewInput(
                    admin_user_id=admin_user_id, actor_type=actor_type, order_id=parsed.order_id,
                    expected_version=parsed.expected_version, action=parsed.action,
                    idempotency_key=idempotency_key, session_id=session_id,
                    request_fingerprint=fingerprint,
                ))
                await state.update_data(confirmation_id=str(confirmation_id), request_fingerprint=fingerprint)
            except Exception:
                await state.clear()
                await query.answer("تعذر تجهيز تأكيد العملية. افتح الطلب من جديد.", show_alert=True)
                return
            await state.set_state(AdminOrderActionState.confirmation)
            await query.answer("تم إنشاء جلسة إدارية حديثة وتأكيد إضافي للعملية. راجع العملية ثم أكد التنفيذ.", show_alert=True)
            await query.message.edit_reply_markup(reply_markup=_confirmation_markup(parsed.order_id, parsed.expected_version))
            return

        if pending_admin != admin_user_id or pending_order != str(parsed.order_id) or pending_version != parsed.expected_version:
            await query.answer("انتهت جلسة العملية أو لم يعد الطلب مطابقًا. افتح الطلب من جديد.", show_alert=True)
            await state.clear()
            return

        if parsed.action == "cancel":
            await state.clear()
            await query.answer("تم إلغاء العملية.")
            await query.message.edit_reply_markup(reply_markup=None)
            return

        if await state.get_state() != AdminOrderActionState.confirmation.state:
            await query.answer("يجب تجهيز العملية وتأكيدها أولًا.", show_alert=True)
            return

        try:
            order_id = UUID(str(data["order_id"]))
            expected_version = int(data["expected_version"])
            action = str(data["order_action"])
            actor_type = str(data["actor_type"])
            session_id = UUID(str(data["session_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await query.answer("بيانات العملية غير صالحة. افتح الطلب من جديد.", show_alert=True)
            return

        response = await handler.handle(
            TelegramAdminReviewInput(
                admin_user_id=admin_user_id,
                actor_type=actor_type,
                order_id=order_id,
                expected_version=expected_version,
                action=action,
                reason=str(data.get("reason")) if data.get("reason") is not None else None,
                idempotency_key=str(data["idempotency_key"]),
                session_id=session_id,
                confirmation_id=UUID(str(data["confirmation_id"])),
                request_fingerprint=str(data["request_fingerprint"]),
            )
        )
        await state.clear()
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
        actor_type = await _resolve_actor_type(resolver, admin_user_id)
        if actor_type is None:
            await state.clear()
            await message.answer("تعذر التحقق من صلاحيات المدير.")
            return
        values = await state.get_data()
        if values.get("admin_user_id") != admin_user_id:
            await state.clear()
            await message.answer("انتهت جلسة العملية. افتح الطلب من جديد.")
            return
        reason = " ".join((message.text or "").split())
        if not 5 <= len(reason) <= MAX_REASON_LENGTH:
            await message.answer("السبب يجب أن يكون بين 5 و1000 حرف.")
            return
        try:
            order_id = UUID(str(values["order_id"]))
            expected_version = int(values["expected_version"])
            action = str(values["order_action"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("بيانات عملية الطلب غير صالحة.")
            return

        session_response = await session_handler.create(admin_user_id, actor_type)
        if not session_response.ok or session_response.session is None:
            await state.clear()
            await message.answer(session_response.message or "تعذر إنشاء جلسة إدارية حديثة.")
            return

        idempotency_key = f"review:{uuid4().hex}"
        session_id = session_response.session.session_id
        fingerprint = AdminOrderReviewService.review_fingerprint(
            order_id, expected_version, admin_user_id, actor_type, action, reason, idempotency_key
        )
        try:
            confirmation_id = await handler.create_confirmation(TelegramAdminReviewInput(
                admin_user_id=admin_user_id,
                actor_type=actor_type,
                order_id=order_id,
                expected_version=expected_version,
                action=action,
                reason=reason,
                idempotency_key=idempotency_key,
                session_id=session_id,
                request_fingerprint=fingerprint,
            ))
        except Exception:
            await state.clear()
            await message.answer("تعذر تجهيز تأكيد العملية. افتح الطلب من جديد.")
            return
        await state.update_data(
            reason=reason,
            actor_type=actor_type,
            session_id=str(session_id),
            idempotency_key=idempotency_key,
            confirmation_id=str(confirmation_id),
            request_fingerprint=fingerprint,
        )
        await state.set_state(AdminOrderActionState.confirmation)
        await message.answer(
            f"العملية: {action}\nسبب العملية:\n{reason}\n\nتم إنشاء جلسة إدارية حديثة وتأكيد إضافي للعملية. هل تريد تأكيد التنفيذ؟",
            reply_markup=_confirmation_markup(order_id, expected_version),
        )

    return router
