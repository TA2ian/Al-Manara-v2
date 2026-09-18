from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.fulfillment import FulfillmentService
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

FULFILLMENT_ERROR_MESSAGE = "تعذر تنفيذ عملية التسليم. حاول مرة أخرى."
FULFILLMENT_CALLBACK = re.compile(r"^admin:fulfillment:(claim|complete|confirm|cancel):([0-9a-fA-F-]{36}):(\d+)$")


class AdminActorTypeResolver(Protocol):
    async def resolve_actor_type(self, telegram_user_id: int) -> str | None: ...


class AdminSessionValidator(Protocol):
    async def validate_session(self, telegram_user_id: int, actor_type: str, session_id: UUID) -> bool: ...


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    idempotency_key: str
    session_id: UUID | None = None
    transfer_reference: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class AdminFulfillmentActionState(StatesGroup):
    confirmation = State()
    transfer_reference = State()
    transfer_reference = State()


def _confirmation_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="تأكيد العملية",
                    callback_data=f"admin:fulfillment:confirm:{order_id}:{expected_version}",
                ),
                InlineKeyboardButton(
                    text="إلغاء",
                    callback_data=f"admin:fulfillment:cancel:{order_id}:{expected_version}",
                ),
            ]
        ]
    )


class TelegramFulfillmentHandler:
    """Framework-neutral adapter; Telegram parsing/authentication stays outside this boundary."""

    def __init__(
        self,
        service: FulfillmentService,
        actor_type_resolver: AdminActorTypeResolver | None = None,
        session_validator: AdminSessionValidator | None = None,
    ) -> None:
        self._service = service
        self._actor_type_resolver = actor_type_resolver
        self._session_validator = session_validator

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
            or not isinstance(request.session_id, UUID)
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
        if operation == "complete" and not isinstance(request.transfer_reference, str):
            return TelegramFulfillmentResponse(False, None, None, False, "أدخل رقم معاملة البلوكتشين أولًا.")
        if self._session_validator is None:
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        try:
            valid = await self._session_validator.validate_session(
                request.admin_user_id, actor_type, request.session_id
            )
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        if not valid:
            return TelegramFulfillmentResponse(False, None, None, False, "انتهت الجلسة الإدارية. أعد فتح العملية.")
        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                internal_order_id=request.order_id,
                expected_version=request.expected_version,
                admin_telegram_user_id=request.admin_user_id,
                actor_type=actor_type,
                idempotency_key=idempotency_key,
                session_id=request.session_id,
                **({"transfer_reference": request.transfer_reference} if operation == "complete" else {}),
            )
        except ValueError:
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        except (PermissionError, LookupError, RuntimeError, OSError):
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, FULFILLMENT_ERROR_MESSAGE)
        return TelegramFulfillmentResponse(True, result.status, result.version, result.replayed, "تم تنفيذ عملية التسليم.")


def fulfillment_action_markup(order_id: UUID, expected_version: int, *, claimed: bool = False):
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


def build_fulfillment_router(
    handler: TelegramFulfillmentHandler,
    session_handler: object,
    actor_type_resolver: AdminActorTypeResolver | None = None,
) -> Router:
    router = Router(name="admin-fulfillment")
    resolver = actor_type_resolver or handler._actor_type_resolver

    @router.callback_query(F.data.regexp(FULFILLMENT_CALLBACK.pattern))
    async def handle_fulfillment(query: CallbackQuery, state: FSMContext) -> None:
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
            await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
            return

        operation, order_id, expected_version = parsed
        data = await state.get_data()

        if operation in {"claim", "complete"}:
            await state.clear()
            session_response = await session_handler.create(admin_user_id, actor_type)  # type: ignore[attr-defined]
            if not session_response.ok or session_response.session is None:
                await query.answer(session_response.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
                return
            await state.update_data(
                admin_user_id=admin_user_id,
                operation=operation,
                order_id=str(order_id),
                expected_version=expected_version,
                actor_type=actor_type,
                session_id=str(session_response.session.session_id),
            )
            if operation == "complete":
                await state.set_state(AdminFulfillmentActionState.transfer_reference)
                await query.answer("الجلسة جاهزة. أرسل الآن TXID/Hash التحويل اليدوي.", show_alert=True)
                await query.message.answer(
                    "قبل الإتمام: تأكد أنك أرسلت صافي USDT الظاهر في تفاصيل الطلب إلى محفظة العميل على BEP20 أو TRC20.\n"
                    "أرسل TXID/Hash للتحويل (64 حرفًا hexadecimal)."
                )
            else:
                await state.set_state(AdminFulfillmentActionState.confirmation)
                await query.answer("تم إنشاء جلسة إدارية حديثة. راجع العملية ثم أكد الاستلام.", show_alert=True)
                await query.message.edit_reply_markup(reply_markup=_confirmation_markup(order_id, expected_version))
            return

        pending_admin = data.get("admin_user_id")
        pending_order = data.get("order_id")
        pending_version = data.get("expected_version")
        if pending_admin != admin_user_id or pending_order != str(order_id) or pending_version != expected_version:
            await state.clear()
            await query.answer("انتهت جلسة العملية أو لم يعد الطلب مطابقًا. افتح الطلب من جديد.", show_alert=True)
            return

        if operation == "cancel":
            await state.clear()
            await query.answer("تم إلغاء العملية.")
            await query.message.edit_reply_markup(reply_markup=None)
            return

        if await state.get_state() != AdminFulfillmentActionState.confirmation.state:
            await query.answer("يجب تجهيز العملية وتأكيدها أولًا.", show_alert=True)
            return

        try:
            stored_order = UUID(str(data["order_id"]))
            stored_version = int(data["expected_version"])
            stored_operation = str(data["operation"])
            stored_actor_type = str(data["actor_type"])
            stored_session = UUID(str(data["session_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await query.answer("بيانات العملية غير صالحة. افتح الطلب من جديد.", show_alert=True)
            return

        if stored_operation == "complete":
            await state.set_state(AdminFulfillmentActionState.transfer_reference)
            await query.answer("بعد تنفيذ تحويل USDT يدويًا، أرسل رقم العملية/مرجع التحويل.", show_alert=True)
            await query.message.answer(
                "نفّذ التحويل يدويًا أولًا إلى محفظة العميل على الشبكة المحددة، ثم أرسل رقم العملية/مرجع التحويل (حتى 200 محرف)."
            )
            return

        request = TelegramFulfillmentInput(
            admin_user_id=admin_user_id,
            actor_type=stored_actor_type,
            order_id=stored_order,
            expected_version=stored_version,
            idempotency_key=str(uuid4()),
            session_id=stored_session,
        )
        response = await handler.claim(request)
        await state.clear()
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok and response.version is not None:
            try:
                await query.message.edit_reply_markup(
                    reply_markup=fulfillment_action_markup(stored_order, response.version, claimed=True)
                )
            except Exception:
                pass

    @router.message(AdminFulfillmentActionState.transfer_reference, F.text)
    async def receive_transfer_reference(message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إرسال مرجع التحويل متاح في المحادثة الخاصة فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await state.clear()
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        data = await state.get_data()
        if data.get("admin_user_id") != admin_user_id:
            await state.clear()
            await message.answer("انتهت جلسة العملية. افتح الطلب من جديد.")
            return
        reference = " ".join((message.text or "").split())
        if not 1 <= len(reference) <= 200:
            await message.answer("مرجع التحويل يجب أن يكون بين 1 و200 محرف.")
            return
        try:
            order_id = UUID(str(data["order_id"]))
            expected_version = int(data["expected_version"])
            actor_type = str(data["actor_type"])
            session_id = UUID(str(data["session_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("بيانات العملية غير صالحة. افتح الطلب من جديد.")
            return
        response = await handler.complete(
            TelegramFulfillmentInput(
                admin_user_id=admin_user_id,
                actor_type=actor_type,
                order_id=order_id,
                expected_version=expected_version,
                idempotency_key=str(uuid4()),
                session_id=session_id,
                manual_usdt_transfer_reference=reference,
            )
        )
        await state.clear()
        await message.answer(response.message)


    @router.message(AdminFulfillmentActionState.transfer_reference)
    async def handle_transfer_reference(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await state.clear()
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        data = await state.get_data()
        try:
            if int(data.get("admin_user_id")) != admin_user_id:
                raise ValueError
            order_id = UUID(str(data["order_id"]))
            expected_version = int(data["expected_version"])
            actor_type = str(data["actor_type"])
            session_id = UUID(str(data["session_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("انتهت جلسة العملية. افتح الطلب من جديد.")
            return
        reference = (message.text or "").strip()
        if len(reference) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in reference):
            await message.answer("TXID غير صالح. أرسل hash من 64 حرفًا hexadecimal فقط.")
            return
        response = await handler.complete(
            TelegramFulfillmentInput(
                admin_user_id=admin_user_id,
                actor_type=actor_type,
                order_id=order_id,
                expected_version=expected_version,
                idempotency_key=str(uuid4()),
                session_id=session_id,
                transfer_reference=reference,
            )
        )
        await state.clear()
        await message.answer(response.message if response.ok else "تعذر إتمام التسليم. قد يكون الطلب تغير أو الجلسة انتهت.")
        if response.ok:
            await message.answer("تم تسجيل التحويل اليدوي وإغلاق الطلب كـ COMPLETED.")

    return router
