from __future__ import annotations

import asyncio
import re
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup
from app.infrastructure.qr_decoder import QRDecodeError, decode_qr_payload
from app.runtime.telegram.admin_payment_account import TelegramAdminPaymentAccountHandler
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

PAYMENT_ACCOUNT_MENU_CALLBACK = "admin:payment_accounts"
PAYMENT_ACCOUNT_CURRENCY_CALLBACK = re.compile(r"^admin:payment:currency:(USD|NEW\.SYP)$")
PAYMENT_ACCOUNT_TOGGLE_CALLBACK = re.compile(r"^admin:payment:toggle:([0-9a-fA-F-]{36}):(USD|NEW\.SYP):(0|1)$")
PAYMENT_ACCOUNT_CONFIRM_CALLBACK = re.compile(r"^admin:payment:confirm:([0-9a-fA-F-]{36})$")
PAYMENT_ACCOUNT_CANCEL_CALLBACK = re.compile(r"^admin:payment:cancel:([0-9a-fA-F-]{36})$")
MAX_ACCOUNT_NAME_LENGTH = 100
MAX_ACCOUNT_NUMBER_LENGTH = 150


class PaymentAccountState(StatesGroup):
    recipient_name = State()
    receiving_address = State()
    qr_image = State()
    confirmation = State()


def payment_account_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ إضافة/تعديل USD", callback_data="admin:payment:currency:USD")],
            [InlineKeyboardButton(text="➕ إضافة/تعديل NEW.SYP", callback_data="admin:payment:currency:NEW.SYP")],
        ]
    )


def payment_account_confirmation_markup(confirmation_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="تأكيد وحفظ", callback_data=f"admin:payment:confirm:{confirmation_id}"),
                InlineKeyboardButton(text="إلغاء", callback_data=f"admin:payment:cancel:{confirmation_id}"),
            ]
        ]
    )


def _currency(value: str) -> CurrencyCode | None:
    try:
        return CurrencyCode(value)
    except ValueError:
        return None


def _normalize_single_line(value: str, *, maximum: int) -> str:
    normalized = " ".join((value or "").split())
    if not normalized or len(normalized) > maximum:
        raise ValueError("invalid text")
    return normalized


async def _download_photo_bytes(message: Message) -> bytes:
    if not message.photo:
        raise ValueError("QR image is required")
    photo = message.photo[-1]
    if photo.file_size is not None and photo.file_size > 5 * 1024 * 1024:
        raise ValueError("QR image exceeds size limit")
    bot = message.bot
    file = await asyncio.wait_for(bot.get_file(photo.file_id), timeout=10)
    if file.file_path is None:
        raise ValueError("QR file path unavailable")
    from io import BytesIO

    target = BytesIO()
    await asyncio.wait_for(bot.download_file(file.file_path, destination=target), timeout=15)
    content = target.getvalue()
    if not content or len(content) > 5 * 1024 * 1024:
        raise ValueError("QR image exceeds size limit")
    return content


async def _resolve_actor_type(resolver: object | None, admin_user_id: int) -> str | None:
    if resolver is None:
        return None
    try:
        actor_type = await resolver.resolve_actor_type(admin_user_id)  # type: ignore[attr-defined]
    except Exception:
        return None
    return actor_type if actor_type in {"primary", "backup"} else None


def build_admin_payment_account_router(
    handler: TelegramAdminPaymentAccountHandler,
    session_handler: TelegramAdminSessionHandler,
    actor_type_resolver: object,
) -> Router:
    router = Router(name="admin-payment-accounts")

    @router.callback_query(F.data == PAYMENT_ACCOUNT_MENU_CALLBACK)
    async def show_payment_accounts(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة حسابات الدفع متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        actor_type = await _resolve_actor_type(actor_type_resolver, user_id)
        if actor_type is None:
            await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
            return
        session = await session_handler.create(user_id, actor_type)
        if not session.ok or session.session is None:
            await query.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
            return
        response = await handler.list(user_id, actor_type, session.session.session_id)
        if not response.ok:
            await query.answer(response.message or "تعذر تحميل حسابات الدفع.", show_alert=True)
            return
        lines = ["💳 حسابات ShamCash", ""]
        for account in response.accounts:
            state = "مفعّل" if account.is_active else "متوقف"
            lines.append(
                f"• {account.currency.value}: {account.account_name} | {account.account_number} | {state}"
            )
        if not response.accounts:
            lines.append("لا توجد حسابات محفوظة بعد.")
        rows = [
            [InlineKeyboardButton(text="➕ إضافة/تعديل USD", callback_data="admin:payment:currency:USD")],
            [InlineKeyboardButton(text="➕ إضافة/تعديل NEW.SYP", callback_data="admin:payment:currency:NEW.SYP")],
        ]
        for account in response.accounts:
            rows.append([
                InlineKeyboardButton(
                    text=f"{'تعطيل' if account.is_active else 'تفعيل'} {account.currency.value}",
                    callback_data=f"admin:payment:toggle:{account.id}:{account.currency.value}:{0 if account.is_active else 1}",
                )
            ])
        await query.answer()
        await query.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.regexp(PAYMENT_ACCOUNT_CURRENCY_CALLBACK.pattern))
    async def start_payment_account_setup(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة حسابات الدفع متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        currency = _currency((query.data or "").rsplit(":", 1)[-1])
        actor_type = await _resolve_actor_type(actor_type_resolver, user_id)
        if currency is None or actor_type is None:
            await query.answer("بيانات العملية غير صالحة.", show_alert=True)
            return
        await state.clear()
        await state.update_data(admin_user_id=user_id, actor_type=actor_type, currency=currency.value)
        await state.set_state(PaymentAccountState.recipient_name)
        await query.answer()
        await query.message.answer(f"إعداد حساب ShamCash — {currency.value}\nأرسل اسم المستفيد (2–{MAX_ACCOUNT_NAME_LENGTH} حرفًا).")

    @router.message(PaymentAccountState.recipient_name, F.text)
    async def receive_recipient_name(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إعداد حساب الدفع متاح في المحادثة الخاصة فقط.")
            return
        try:
            recipient_name = _normalize_single_line(message.text or "", maximum=MAX_ACCOUNT_NAME_LENGTH)
        except ValueError:
            await message.answer(f"الاسم يجب أن يكون بين 2 و{MAX_ACCOUNT_NAME_LENGTH} حرفًا.")
            return
        await state.update_data(recipient_name=recipient_name)
        await state.set_state(PaymentAccountState.receiving_address)
        await message.answer(f"أرسل رقم/معرّف ShamCash (5–{MAX_ACCOUNT_NUMBER_LENGTH} حرفًا).")

    @router.message(PaymentAccountState.receiving_address, F.text)
    async def receive_receiving_address(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إعداد حساب الدفع متاح في المحادثة الخاصة فقط.")
            return
        try:
            receiving_address = _normalize_single_line(message.text or "", maximum=MAX_ACCOUNT_NUMBER_LENGTH)
        except ValueError:
            await message.answer(f"المعرّف يجب أن يكون بين 5 و{MAX_ACCOUNT_NUMBER_LENGTH} حرفًا.")
            return
        await state.update_data(receiving_address=receiving_address)
        await state.set_state(PaymentAccountState.qr_image)
        await message.answer("أرسل صورة QR الخاصة بحساب ShamCash. سيتم فك QR والتحقق من مطابقته للمعرّف الذي أدخلته.")

    @router.message(PaymentAccountState.qr_image, F.photo)
    async def receive_qr_image(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            await message.answer("إعداد حساب الدفع متاح في المحادثة الخاصة فقط.")
            return
        try:
            content = await _download_photo_bytes(message)
            qr_payload = await asyncio.wait_for(asyncio.to_thread(decode_qr_payload, content), timeout=10)
        except (QRDecodeError, ValueError, OSError):
            await message.answer("تعذر التحقق من QR. أرسل صورة واضحة وصالحة ضمن الحجم المسموح.")
            return
        values = await state.get_data()
        admin_user_id = values.get("admin_user_id")
        actor_type = values.get("actor_type")
        currency = _currency(str(values.get("currency", "")))
        recipient_name = str(values.get("recipient_name", ""))
        receiving_address = str(values.get("receiving_address", ""))
        if not isinstance(admin_user_id, int) or actor_type not in {"primary", "backup"} or currency is None:
            await state.clear()
            await message.answer("انتهت جلسة الإعداد. ابدأ العملية من جديد.")
            return
        try:
            setup = PaymentMethodSetup(
                recipient_name=recipient_name,
                receiving_address=receiving_address,
                qr_address=qr_payload,
                qr_image_file_id=message.photo[-1].file_id,
            )
        except ValueError:
            await message.answer("QR لا يطابق المعرّف المدخل. أعد إرسال QR المطابق.")
            return
        session = await session_handler.create(admin_user_id, actor_type)
        if not session.ok or session.session is None:
            await state.clear()
            await message.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.")
            return
        response = await handler.request_upsert_confirmation(
            admin_user_id,
            actor_type,
            currency,
            setup,
            session.session.session_id,
        )
        if not response.ok or response.confirmation_id is None:
            await state.clear()
            await message.answer(response.message or "تعذر تجهيز التأكيد.")
            return
        confirmation_id = response.confirmation_id
        await state.update_data(
            session_id=str(session.session.session_id),
            confirmation_id=str(confirmation_id),
            recipient_name=setup.recipient_name,
            receiving_address=setup.receiving_address,
            qr_address=setup.qr_address,
            qr_image_file_id=setup.qr_image_file_id,
        )
        await state.set_state(PaymentAccountState.confirmation)
        await message.answer(
            "راجع بيانات حساب ShamCash قبل الحفظ:\n"
            f"العملة: {currency.value}\n"
            f"المستفيد: {setup.recipient_name}\n"
            f"المعرّف: {setup.receiving_address}\n"
            f"QR: تم التحقق والمطابقة\n\n"
            "التغيير لن يُحفظ إلا بعد الضغط على «تأكيد وحفظ».",
            reply_markup=payment_account_confirmation_markup(confirmation_id),
        )

    @router.callback_query(F.data.regexp(PAYMENT_ACCOUNT_CONFIRM_CALLBACK.pattern))
    async def confirm_payment_account(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة حسابات الدفع متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        match = PAYMENT_ACCOUNT_CONFIRM_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("هذا التأكيد غير صالح.", show_alert=True)
            return
        values = await state.get_data()
        if values.get("admin_user_id") != user_id or values.get("confirmation_id") != match.group(1):
            await state.clear()
            await query.answer("انتهت جلسة العملية أو لا تطابق هذا الحساب.", show_alert=True)
            return
        if await state.get_state() != PaymentAccountState.confirmation.state:
            await state.clear()
            await query.answer("انتهت جلسة العملية. ابدأ من جديد.", show_alert=True)
            return
        actor_type = str(values.get("actor_type", ""))
        currency = _currency(str(values.get("currency", "")))
        try:
            session_id = UUID(str(values["session_id"]))
            confirmation_id = UUID(str(values["confirmation_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await query.answer("بيانات التأكيد غير صالحة. ابدأ من جديد.", show_alert=True)
            return
        if currency is None or actor_type not in {"primary", "backup"}:
            await state.clear()
            await query.answer("بيانات التأكيد غير صالحة.", show_alert=True)
            return
        if values.get("operation") == "status":
            response = await handler.confirm_set_active(
                user_id,
                actor_type,
                currency,
                bool(values.get("is_active")),
                session_id,
                confirmation_id,
            )
        else:
            try:
                setup = PaymentMethodSetup(
                    recipient_name=str(values["recipient_name"]),
                    receiving_address=str(values["receiving_address"]),
                    qr_address=str(values["qr_address"]),
                    qr_image_file_id=str(values["qr_image_file_id"]),
                )
            except (KeyError, TypeError, ValueError):
                await state.clear()
                await query.answer("بيانات التأكيد غير صالحة. ابدأ من جديد.", show_alert=True)
                return
            response = await handler.confirm_upsert(
                user_id, actor_type, currency, setup, session_id, confirmation_id
            )
        await state.clear()
        await query.answer(response.message or "تعذر حفظ الحساب.", show_alert=not response.ok)
        if response.ok:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.callback_query(F.data.regexp(PAYMENT_ACCOUNT_CANCEL_CALLBACK.pattern))
    async def cancel_payment_account(query: CallbackQuery, state: FSMContext) -> None:
        match = PAYMENT_ACCOUNT_CANCEL_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("هذا التأكيد غير صالح.", show_alert=True)
            return
        values = await state.get_data()
        user_id = authenticated_telegram_user_id(query)
        if user_id is None or values.get("admin_user_id") != user_id or values.get("confirmation_id") != match.group(1):
            await state.clear()
            await query.answer("انتهت جلسة العملية.", show_alert=True)
            return
        await state.clear()
        await query.answer("تم إلغاء العملية.")
        if query.message is not None:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.callback_query(F.data.regexp(PAYMENT_ACCOUNT_TOGGLE_CALLBACK.pattern))
    async def request_toggle_payment_account(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("إدارة حسابات الدفع متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        match = PAYMENT_ACCOUNT_TOGGLE_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        actor_type = await _resolve_actor_type(actor_type_resolver, user_id)
        if actor_type is None:
            await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
            return
        currency = _currency(match.group(2))
        is_active = match.group(3) == "1"
        if currency is None:
            await query.answer("العملة غير صالحة.", show_alert=True)
            return
        session = await session_handler.create(user_id, actor_type)
        if not session.ok or session.session is None:
            await query.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
            return
        response = await handler.request_set_active_confirmation(
            user_id, actor_type, currency, is_active, session.session.session_id
        )
        if not response.ok or response.confirmation_id is None:
            await query.answer(response.message or "تعذر تجهيز التأكيد.", show_alert=True)
            return
        await state.clear()
        await state.update_data(
            admin_user_id=user_id,
            actor_type=actor_type,
            currency=currency.value,
            is_active=is_active,
            operation="status",
            session_id=str(session.session.session_id),
            confirmation_id=str(response.confirmation_id),
        )
        await state.set_state(PaymentAccountState.confirmation)
        await query.answer()
        await query.message.answer(
            f"تغيير حالة حساب ShamCash — {currency.value}\n"
            f"الحالة الجديدة: {'مفعّل' if is_active else 'متوقف'}\n\n"
            "هل تريد تأكيد التغيير؟",
            reply_markup=payment_account_confirmation_markup(response.confirmation_id),
        )

    return router
