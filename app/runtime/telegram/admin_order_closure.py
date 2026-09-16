from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.admin_order_closure import (
    AdminOrderClosureCommand,
    AdminOrderClosureService,
    MAX_REASON_LENGTH,
    MIN_REASON_LENGTH,
)
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

CLOSURE_ERROR_MESSAGE = "The order could not be closed. Please retry."
CLOSURE_CALLBACK = re.compile(r"^admin:closure:(request|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$")


class AdminActorTypeResolver(Protocol):
    async def resolve_actor_type(self, telegram_user_id: int) -> str | None: ...


class AdminClosureState(StatesGroup):
    awaiting_reason = State()
    awaiting_confirmation = State()


@dataclass(frozen=True, slots=True)
class TelegramAdminClosureInput:
    admin_user_id: int
    order_id: UUID
    expected_version: int
    session_id: UUID
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramAdminClosureResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class TelegramAdminOrderClosureHandler:
    """Framework-neutral adapter for the privileged no-fulfillment closure."""

    def __init__(
        self,
        service: AdminOrderClosureService,
        actor_type_resolver: AdminActorTypeResolver | None = None,
    ) -> None:
        self._service = service
        self._actor_type_resolver = actor_type_resolver

    async def handle(self, request: TelegramAdminClosureInput) -> TelegramAdminClosureResponse:
        if request.admin_user_id <= 0 or request.expected_version < 1:
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        if not isinstance(request.reason, str):
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        normalized_reason = " ".join(request.reason.split())
        if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        if not isinstance(request.idempotency_key, str) or not request.idempotency_key.strip():
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        try:
            result = await self._service.close_without_fulfillment(
                AdminOrderClosureCommand(
                    internal_order_id=request.order_id,
                    admin_telegram_user_id=request.admin_user_id,
                    expected_version=request.expected_version,
                    session_id=request.session_id,
                    reason=normalized_reason,
                    idempotency_key=request.idempotency_key,
                )
            )
        except Exception:
            return TelegramAdminClosureResponse(False, None, None, False, CLOSURE_ERROR_MESSAGE)

        return TelegramAdminClosureResponse(
            True, result.status, result.version, result.replayed, "Order closed without fulfillment."
        )


def _confirmation_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="تأكيد الإغلاق", callback_data=f"admin:closure:confirm:{order_id}:{expected_version}"),
                InlineKeyboardButton(text="إلغاء", callback_data=f"admin:closure:cancel:{order_id}:{expected_version}"),
            ]
        ]
    )


def parse_closure_callback(data: str | None) -> tuple[str, UUID, int] | None:
    match = CLOSURE_CALLBACK.fullmatch(data or "")
    if match is None:
        return None
    try:
        return match.group(1), UUID(match.group(2)), int(match.group(3))
    except ValueError:
        return None


def build_admin_order_closure_router(
    handler: TelegramAdminOrderClosureHandler,
    session_handler: TelegramAdminSessionHandler,
    actor_type_resolver: AdminActorTypeResolver | None = None,
) -> Router:
    router = Router(name="admin-order-closure")

    @router.callback_query(F.data.regexp(CLOSURE_CALLBACK.pattern))
    async def handle_closure(query: CallbackQuery, state: FSMContext) -> None:
        parsed = parse_closure_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if query.message is None or not is_private_message(query.message):
            await query.answer("الإغلاق الإداري متاح في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return

        actor_type = None
        if actor_type_resolver is not None:
            try:
                actor_type = await actor_type_resolver.resolve_actor_type(admin_user_id)
            except Exception:
                await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
                return
            if actor_type is None:
                await query.answer("غير مصرح لك بهذه العملية.", show_alert=True)
                return

        operation, order_id, expected_version = parsed
        data = await state.get_data()
        pending_admin = data.get("admin_user_id")
        pending_order = data.get("order_id")
        pending_version = data.get("expected_version")

        if operation == "request":
            await state.set_state(AdminClosureState.awaiting_reason)
            await state.set_data({
                "admin_user_id": admin_user_id,
                "order_id": str(order_id),
                "expected_version": expected_version,
            })
            await query.answer("أرسل سبب الإغلاق.", show_alert=True)
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(
                f"أرسل سبب الإغلاق الإداري فقط (من {MIN_REASON_LENGTH} إلى {MAX_REASON_LENGTH} حرفًا).\n"
                "سيُحفظ كنص تدقيقي فقط ولن يتم تفسيره أو تنفيذه."
            )
            return

        if pending_admin != admin_user_id or pending_order != str(order_id) or pending_version != expected_version:
            await query.answer("انتهت جلسة الإغلاق أو لم يعد الطلب مطابقًا. افتح الطلب من جديد.", show_alert=True)
            await state.clear()
            return

        if operation == "cancel":
            await state.clear()
            await query.answer("تم إلغاء الإغلاق.")
            await query.message.edit_reply_markup(reply_markup=None)
            return

        if await state.get_state() != AdminClosureState.awaiting_confirmation.state:
            await query.answer("يجب إرسال سبب الإغلاق وتأكيده أولًا.", show_alert=True)
            return

        session_response = await session_handler.create(admin_user_id, actor_type or "primary")
        if not session_response.ok or session_response.session is None:
            await query.answer(session_response.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
            return

        response = await handler.handle(
            TelegramAdminClosureInput(
                admin_user_id=admin_user_id,
                order_id=order_id,
                expected_version=expected_version,
                session_id=session_response.session.session_id,
                reason=str(data.get("reason", "")),
                idempotency_key=str(uuid4()),
            )
        )
        await state.clear()
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.message(AdminClosureState.awaiting_reason)
    async def receive_reason(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await state.clear()
            return
        data = await state.get_data()
        if data.get("admin_user_id") != admin_user_id:
            await state.clear()
            return
        reason = " ".join((message.text or "").split())
        if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
            await message.answer(f"سبب الإغلاق يجب أن يكون بين {MIN_REASON_LENGTH} و{MAX_REASON_LENGTH} حرفًا.")
            return
        try:
            order_id = UUID(str(data["order_id"]))
            expected_version = int(data["expected_version"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("انتهت جلسة الإغلاق. افتح الطلب من جديد.")
            return
        await state.update_data(reason=reason)
        await state.set_state(AdminClosureState.awaiting_confirmation)
        await message.answer(
            f"سبب الإغلاق:\n{reason}\n\nهل تريد تأكيد إغلاق الطلب دون تنفيذ؟",
            reply_markup=_confirmation_markup(order_id, expected_version),
        )

    return router
