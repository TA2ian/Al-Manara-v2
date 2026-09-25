from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.admin_action_confirmation import AdminActionConfirmationService
from app.application.admin_order_recovery import (
    AdminOrderRecoveryService,
    AdminOrderRecoveryCommand,
    MAX_REASON_LENGTH,
    MIN_REASON_LENGTH,
)
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message


REOPEN_RECEIPT_CALLBACK = re.compile(r"^admin:receipt-reopen:(request|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$")


class ReceiptReopenState(StatesGroup):
    reason = State()
    confirmation = State()


class ActorResolver(Protocol):
    async def resolve_actor_type(self, telegram_user_id: int) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ReceiptReopenResponse:
    ok: bool
    message: str
    version: int | None = None


class TelegramAdminReceiptReopenHandler:
    def __init__(self, service: AdminOrderRecoveryService, resolver: ActorResolver, confirmations: AdminActionConfirmationService) -> None:
        self._service = service
        self._resolver = resolver
        self._confirmations = confirmations

    @staticmethod
    def fingerprint(
        order_id: UUID,
        expected_version: int,
        admin_user_id: int,
        actor_type: str,
        reason: str,
    ) -> str:
        canonical = "|".join((
            "order.reopen_receipt",
            str(order_id),
            str(expected_version),
            str(admin_user_id),
            actor_type,
            " ".join(reason.split()),
        ))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def handle(
        self,
        *,
        admin_user_id: int,
        actor_type: str,
        order_id: UUID,
        expected_version: int,
        session_id: UUID,
        confirmation_id: UUID,
        request_fingerprint: str,
        reason: str,
    ) -> ReceiptReopenResponse:
        try:
            result = await self._service.reopen_for_receipt(
                AdminOrderRecoveryCommand(
                    internal_order_id=order_id,
                    admin_telegram_user_id=admin_user_id,
                    actor_type=actor_type,
                    expected_version=expected_version,
                    session_id=session_id,
                    confirmation_id=confirmation_id,
                    request_fingerprint=request_fingerprint,
                    reason=reason,
                    idempotency_key=str(uuid4()),
                )
            )
        except Exception:
            return ReceiptReopenResponse(False, "تعذر إعادة فتح الطلب للمراجعة. افتح الطلب من جديد وحاول مرة أخرى.")
        return ReceiptReopenResponse(
            True,
            "تم فتح الطلب لاستقبال إيصال جديد.",
            result.version,
        )


def receipt_reopen_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="إعادة طلب الإيصال",
            callback_data=f"admin:receipt-reopen:request:{order_id}:{expected_version}",
        )
    ]])


def _confirm_reopen_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="تأكيد إعادة طلب الإيصال", callback_data=f"admin:receipt-reopen:confirm:{order_id}:{expected_version}"),
        InlineKeyboardButton(text="إلغاء", callback_data=f"admin:receipt-reopen:cancel:{order_id}:{expected_version}"),
    ]])


def build_admin_receipt_reopen_router(
    handler: TelegramAdminReceiptReopenHandler,
    session_handler: TelegramAdminSessionHandler,
) -> Router:
    router = Router(name="admin-order-recovery")

    @router.callback_query(F.data.regexp(REOPEN_RECEIPT_CALLBACK.pattern))
    async def callback(query: CallbackQuery, state: FSMContext) -> None:
        match = REOPEN_RECEIPT_CALLBACK.fullmatch(query.data or "")
        if match is None or query.message is None or not is_private_message(query.message):
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        admin_id = authenticated_telegram_user_id(query)
        if admin_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        actor = await handler._resolver.resolve_actor_type(admin_id)
        if actor not in {"primary", "backup"}:
            await query.answer("غير مصرح لك.", show_alert=True)
            return
        action, order_id_text, version_text = match.groups()
        order_id = UUID(order_id_text)
        version = int(version_text)
        if action == "request":
            session = await session_handler.create(admin_id, actor)
            if not session.ok or session.session is None:
                await query.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
                return
            await state.clear()
            await state.update_data(
                admin_id=admin_id,
                actor_type=actor,
                order_id=str(order_id),
                expected_version=version,
                session_id=str(session.session.session_id),
            )
            await state.set_state(ReceiptReopenState.reason)
            await query.answer("أرسل سبب إعادة طلب الإيصال.", show_alert=True)
            await query.message.answer(
                f"أرسل سبب إعادة طلب الإيصال (من {MIN_REASON_LENGTH} إلى {MAX_REASON_LENGTH} حرفًا)."
            )
            return

        data = await state.get_data()
        if data.get("admin_id") != admin_id or data.get("order_id") != str(order_id) or data.get("expected_version") != version:
            await state.clear()
            await query.answer("انتهت جلسة العملية. افتح الطلب من جديد.", show_alert=True)
            return
        if action == "cancel":
            await state.clear()
            await query.answer("تم الإلغاء.")
            return
        if await state.get_state() != ReceiptReopenState.confirmation.state:
            await query.answer("أكمل سبب إعادة طلب الإيصال أولًا.", show_alert=True)
            return

        try:
            session_id = UUID(str(data["session_id"]))
            confirmation_id = UUID(str(data["confirmation_id"]))
            fingerprint = str(data["fingerprint"])
            reason = str(data["reason"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await query.answer("بيانات العملية غير صالحة.", show_alert=True)
            return

        result = await handler.handle(
            admin_user_id=admin_id,
            actor_type=actor,
            order_id=order_id,
            expected_version=version,
            session_id=session_id,
            confirmation_id=confirmation_id,
            request_fingerprint=fingerprint,
            reason=reason,
        )
        await state.clear()
        await query.answer(result.message, show_alert=not result.ok)

    @router.message(ReceiptReopenState.reason, F.text)
    async def reason(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            return
        admin_id = authenticated_telegram_user_id(message)
        if admin_id is None:
            await state.clear()
            return
        data = await state.get_data()
        if data.get("admin_id") != admin_id:
            await state.clear()
            return
        text = " ".join((message.text or "").split())
        if not MIN_REASON_LENGTH <= len(text) <= MAX_REASON_LENGTH:
            await message.answer(f"السبب يجب أن يكون بين {MIN_REASON_LENGTH} و{MAX_REASON_LENGTH} حرفًا.")
            return
        actor = await handler._resolver.resolve_actor_type(admin_id)
        if actor not in {"primary", "backup"}:
            await state.clear()
            await message.answer("غير مصرح لك.")
            return
        session_id = UUID(str(data["session_id"]))
        fingerprint = handler.fingerprint(UUID(str(data["order_id"])), int(data["expected_version"]), admin_id, actor, text)
        # The confirmation is created only after the exact operation fingerprint exists.
        confirmation = await _create_confirmation(handler._confirmations, admin_id, actor, session_id, fingerprint)
        if confirmation is None:
            await state.clear()
            await message.answer("تعذر إنشاء تأكيد العملية.")
            return
        confirmation_id, _ = confirmation
        await state.update_data(
            actor_type=actor,
            reason=text,
            fingerprint=fingerprint,
            confirmation_id=str(confirmation_id),
        )
        await state.set_state(ReceiptReopenState.confirmation)
        await message.answer(
            f"العملية: إعادة طلب إيصال جديد\nالسبب:\n{text}\n\nهل تريد المتابعة؟",
            reply_markup=_confirm_markup(UUID(str(data["order_id"])), int(data["expected_version"])),
        )

    return router


async def _create_confirmation(service: AdminActionConfirmationService, admin_id: int, actor: str, session_id: UUID, fingerprint: str):
    try:
        confirmation_id = await service.create(admin_id, actor, session_id, "order.reopen_receipt", fingerprint)
        return confirmation_id, None
    except Exception:
        return None
