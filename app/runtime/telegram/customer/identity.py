from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.composition_root import CustomerComposition
from app.runtime.telegram.customer_identity import TelegramCustomerIdentityInput
from app.runtime.telegram.messages import customer_safe_message
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

IDENTITY_RETRY_MESSAGE = "تعذر إرسال طلب التحقق حاليًا. حاول لاحقًا."
PRIVATE_CHAT_REQUIRED = "حفاظًا على خصوصيتك، أكمل التحقق في محادثة خاصة مع البوت."


class IdentityVerificationState(StatesGroup):
    contact = State()
    full_name = State()
    shamcash_account = State()
    qr_image = State()


async def _require_private(message: Message, state: FSMContext | None = None) -> bool:
    if is_private_message(message):
        return True
    if state is not None:
        await state.clear()
    await message.answer(PRIVATE_CHAT_REQUIRED)
    return False


def build_customer_identity_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer-identity")

    @router.message(Command("verify"))
    async def begin_identity_verification(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer(IDENTITY_RETRY_MESSAGE)
            return
        await state.clear()
        await state.set_state(IdentityVerificationState.contact)
        await message.answer(
            "للبدء، أرسل رقمك من خلال زر «مشاركة رقم الهاتف».",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="مشاركة رقم الهاتف", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

    @router.message(IdentityVerificationState.contact, F.contact)
    async def receive_identity_contact(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        user_id = authenticated_telegram_user_id(message)
        contact = message.contact
        if user_id is None or contact is None or contact.user_id != user_id or not contact.phone_number:
            await message.answer("يجب مشاركة رقم الهاتف المرتبط بحساب Telegram نفسه.")
            return
        await state.update_data(telegram_contact_phone=contact.phone_number)
        await state.set_state(IdentityVerificationState.full_name)
        await message.answer(
            "أرسل اسمك الثلاثي كما يظهر في حساب Sham Cash.",
            reply_markup=ReplyKeyboardRemove(),
        )

    @router.message(IdentityVerificationState.contact)
    async def require_identity_contact(message: Message, state: FSMContext) -> None:
        if await _require_private(message, state):
            await message.answer("استخدم زر «مشاركة رقم الهاتف» لإرسال رقمك المرتبط بحساب Telegram.")

    @router.message(IdentityVerificationState.full_name, F.text)
    async def receive_identity_name(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        full_name = (message.text or "").strip()
        if not 1 <= len(full_name) <= 200:
            await message.answer("أرسل اسمًا صالحًا بطول مناسب.")
            return
        await state.update_data(full_name=full_name)
        await state.set_state(IdentityVerificationState.shamcash_account)
        await message.answer("أرسل رقم أو معرّف حساب Sham Cash الخاص بك.")

    @router.message(IdentityVerificationState.shamcash_account, F.text)
    async def receive_identity_account(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        account = (message.text or "").strip()
        if not 1 <= len(account) <= 100:
            await message.answer("أرسل رقم أو معرّف حساب Sham Cash صالحًا.")
            return
        await state.update_data(shamcash_account=account)
        await state.set_state(IdentityVerificationState.qr_image)
        await message.answer("أرسل الآن صورة QR الخاصة بحساب Sham Cash.")

    @router.message(IdentityVerificationState.qr_image, F.photo)
    async def receive_identity_qr(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        user_id = authenticated_telegram_user_id(message)
        values = await state.get_data()
        photo = message.photo[-1] if message.photo else None
        if user_id is None or photo is None:
            await state.clear()
            await message.answer(IDENTITY_RETRY_MESSAGE)
            return
        response = await composition.identity.submit(
            TelegramCustomerIdentityInput(
                telegram_user_id=user_id,
                full_name=str(values.get("full_name", "")),
                shamcash_account=str(values.get("shamcash_account", "")),
                telegram_contact_phone=str(values.get("telegram_contact_phone", "")),
                qr_image_file_id=photo.file_id,
            )
        )
        await state.clear()
        await message.answer(customer_safe_message(response.message, IDENTITY_RETRY_MESSAGE))

    @router.message(IdentityVerificationState.qr_image)
    async def require_identity_qr(message: Message, state: FSMContext) -> None:
        if await _require_private(message, state):
            await message.answer("أرسل صورة QR كصورة، وليس ملفًا أو نصًا.")

    return router