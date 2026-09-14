from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.application.admin_order_closure import (
    AdminOrderClosureCommand,
    AdminOrderClosureService,
)
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

CLOSURE_ERROR_MESSAGE = "The order could not be closed. Please retry."
CLOSURE_CALLBACK = re.compile(r"^admin:closure:(request|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$")
STANDARD_CLOSURE_REASON = "إغلاق إداري دون تنفيذ"


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

    def __init__(self, service: AdminOrderClosureService) -> None:
        self._service = service

    async def handle(
        self, request: TelegramAdminClosureInput
    ) -> TelegramAdminClosureResponse:
        if request.admin_user_id <= 0 or request.expected_version < 1:
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        if not request.reason.strip() or not request.idempotency_key.strip():
            return TelegramAdminClosureResponse(False, None, None, False, "invalid closure request")
        try:
            result = await self._service.close_without_fulfillment(
                AdminOrderClosureCommand(
                    internal_order_id=request.order_id,
                    admin_telegram_user_id=request.admin_user_id,
                    expected_version=request.expected_version,
                    session_id=request.session_id,
                    reason=request.reason,
                    idempotency_key=request.idempotency_key,
                )
            )
        except ValueError:
            return TelegramAdminClosureResponse(
                False,
                None,
                None,
                False,
                CLOSURE_ERROR_MESSAGE,
            )
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramAdminClosureResponse(
                False, None, None, False, CLOSURE_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminClosureResponse(False, None, None, False, "The closure operation failed.")

        return TelegramAdminClosureResponse(
            True,
            result.status,
            result.version,
            result.replayed,
            "Order closed without fulfillment.",
        )


def _confirmation_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="تأكيد الإغلاق",
                    callback_data=f"admin:closure:confirm:{order_id}:{expected_version}",
                ),
                InlineKeyboardButton(
                    text="إلغاء",
                    callback_data=f"admin:closure:cancel:{order_id}:{expected_version}",
                ),
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
) -> Router:
    router = Router(name="admin-order-closure")

    @router.callback_query(F.data.regexp(CLOSURE_CALLBACK.pattern))
    async def handle_closure(query: CallbackQuery) -> None:
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
        operation, order_id, expected_version = parsed
        if operation == "request":
            await query.answer("يتطلب الإغلاق تأكيدًا إضافيًا.", show_alert=True)
            await query.message.edit_reply_markup(
                reply_markup=_confirmation_markup(order_id, expected_version)
            )
            return
        if operation == "cancel":
            await query.answer("تم إلغاء الإغلاق.")
            await query.message.edit_reply_markup(reply_markup=None)
            return

        session_response = await session_handler.create(admin_user_id, "primary")
        if not session_response.ok or session_response.session is None:
            await query.answer(
                session_response.message or "تعذر إنشاء جلسة إدارية حديثة.",
                show_alert=True,
            )
            return
        response = await handler.handle(
            TelegramAdminClosureInput(
                admin_user_id=admin_user_id,
                order_id=order_id,
                expected_version=expected_version,
                session_id=session_response.session.session_id,
                reason=STANDARD_CLOSURE_REASON,
                idempotency_key=str(uuid4()),
            )
        )
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    return router
