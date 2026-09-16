from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.application.fulfillment import FulfillmentService
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

FULFILLMENT_ERROR_MESSAGE = "تعذر تنفيذ عملية التسليم. حاول مرة أخرى."
FULFILLMENT_CALLBACK = re.compile(r"^admin:fulfillment:(claim|complete):([0-9a-fA-F-]{36}):(\d+)$")
CLOSURE_CALLBACK = re.compile(r"^admin:closure:(request|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$")


class AdminActorTypeResolver(Protocol):
    async def resolve_actor_type(self, telegram_user_id: int) -> str | None: ...


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class TelegramFulfillmentHandler:
    """Framework-neutral adapter; Telegram parsing/authentication stays outside this boundary."""

    def __init__(self, service: FulfillmentService, actor_type_resolver: AdminActorTypeResolver | None = None) -> None:
        self._service = service
        self._actor_type_resolver = actor_type_resolver

    async def claim(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="claim")

    async def complete(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="complete")

    async def _run(self, request: TelegramFulfillmentInput, operation: str) -> TelegramFulfillmentResponse:
        if (
            not isinstance(request.admin_user_id, int)
            or request.admin_user_id <= 0
            or not isinstance(request.expected_version, int)
            or request.expected_version < 1
            or not isinstance(request.order_id, UUID)
            or not isinstance(request.actor_type, str)
            or not isinstance(request.idempotency_key, str)
        ):
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        actor_type = request.actor_type.strip().lower()
        if self._actor_type_resolver is not None:
            try:
                resolved = await self._actor_type_resolver.resolve_actor_type(request.admin_user_id)
            except Exception:
                return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
            if resolved is None:
                return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
            actor_type = resolved
        idempotency_key = request.idempotency_key.strip()
        if actor_type not in {"primary", "backup"} or not 1 <= len(idempotency_key) <= 128:
            return TelegramFulfillmentResponse(False, None, None, False, "invalid fulfillment request")
        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                internal_order_id=request.order_id,
                expected_version=request.expected_version,
                admin_telegram_user_id=request.admin_user_id,
                actor_type=actor_type,
                idempotency_key=idempotency_key,
            )
        except ValueError:
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, "تعذر تنفيذ عملية التسليم.")
        return TelegramFulfillmentResponse(True, result.status, result.version, result.replayed, "تم تنفيذ عملية التسليم.")


def fulfillment_action_markup(order_id: UUID, expected_version: int, *, claimed: bool = False):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    action = "complete" if claimed else "claim"
    label = "إتمام التسليم" if claimed else "استلام للتنفيذ"
    rows = [[InlineKeyboardButton(text=label, callback_data=f"admin:fulfillment:{action}:{order_id}:{expected_version}")]]
    if not claimed:
        rows.append([InlineKeyboardButton(text="إغلاق دون تنفيذ", callback_data=f"admin:closure:request:{order_id}:{expected_version}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_fulfillment_callback(data: str | None) -> tuple[str, UUID, int] | None:
    match = FULFILLMENT_CALLBACK.fullmatch(data or "")
    if match is None:
        return None
    try:
        return match.group(1), UUID(match.group(2)), int(match.group(3))
    except ValueError:
        return None


def build_fulfillment_router(handler: TelegramFulfillmentHandler, actor_type_resolver: AdminActorTypeResolver | None = None) -> Router:
    router = Router(name="admin-fulfillment")
    resolver = actor_type_resolver or handler._actor_type_resolver

    @router.callback_query(F.data.regexp(FULFILLMENT_CALLBACK.pattern))
    async def handle_fulfillment(query: CallbackQuery) -> None:
        parsed = parse_fulfillment_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة التسليم متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        operation, order_id, expected_version = parsed
        actor_type = None
        if resolver is not None:
            try:
                actor_type = await resolver.resolve_actor_type(admin_user_id)
            except Exception:
                await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
                return
            if actor_type is None:
                await query.answer("غير مصرح لك بهذه العملية.", show_alert=True)
                return
        else:
            actor_type = "primary"
        request = TelegramFulfillmentInput(
            admin_user_id=admin_user_id,
            actor_type=actor_type,
            order_id=order_id,
            expected_version=expected_version,
            idempotency_key=str(uuid4()),
        )
        response = await (handler.claim(request) if operation == "claim" else handler.complete(request))
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok:
            try:
                if operation == "claim" and response.version is not None:
                    await query.message.edit_reply_markup(reply_markup=fulfillment_action_markup(order_id, response.version, claimed=True))
                else:
                    await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    return router
