from __future__ import annotations

import re
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.composition_root import CustomerComposition
from app.domain.wallet_registration import SUPPORTED_WALLET_NETWORKS
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message
from app.runtime.telegram.wallets import (
    TelegramWalletInput,
    TelegramWalletRegistrationInput,
    WalletMessages,
)

PRIVATE_CHAT_REQUIRED = "حفاظًا على خصوصيتك، أدر محافظك في محادثة خاصة مع البوت."
WALLET_RETRY_MESSAGE = "تعذر تنفيذ عملية المحفظة حاليًا. حاول لاحقًا."
WALLET_CANCELLED_MESSAGE = "تم إلغاء إضافة المحفظة. يمكنك البدء من جديد باستخدام /wallet_add."
WALLET_ADD_CALLBACK = "wallet:add"
WALLET_LIST_CALLBACK = "wallet:list"
WALLET_CANCEL_CALLBACK = "wallet:cancel"
WALLET_DISABLE_CALLBACK_PREFIX = "wallet:disable:"
WALLET_DISABLE_CONFIRM_PREFIX = "wallet:disable:confirm:"
UUID_IN_LISTING = re.compile(
    r"\(([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)"
)


class WalletRegistrationState(StatesGroup):
    network = State()
    address = State()
    label = State()
    qr = State()


def wallet_management_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ إضافة محفظة", callback_data=WALLET_ADD_CALLBACK)],
            [InlineKeyboardButton(text="🔄 تحديث المحافظ", callback_data=WALLET_LIST_CALLBACK)],
            [InlineKeyboardButton(text="🏠 لوحة المنارة", callback_data="customer:dashboard")],
        ]
    )


def wallet_listing_markup(text: str) -> InlineKeyboardMarkup:
    wallet_ids = _wallet_ids_from_listing(text)
    rows = [
        [
            InlineKeyboardButton(
                text="تعطيل المحفظة",
                callback_data=f"{WALLET_DISABLE_CALLBACK_PREFIX}{wallet_id}",
            )
        ]
        for wallet_id in wallet_ids
    ]
    rows.extend(wallet_management_markup().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _network_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=network,
                callback_data=f"wallet:network:{network}",
            )
        ]
        for network in sorted(SUPPORTED_WALLET_NETWORKS)
    ]
    rows.append([InlineKeyboardButton(text="إلغاء", callback_data=WALLET_CANCEL_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="إلغاء", callback_data=WALLET_CANCEL_CALLBACK)]]
    )


def _wallet_ids_from_listing(text: str) -> tuple[UUID, ...]:
    """Extract IDs emitted by TelegramWalletHandler for disable buttons."""

    ids: list[UUID] = []
    for value in UUID_IN_LISTING.findall(text):
        try:
            ids.append(UUID(value))
        except ValueError:
            continue
    return tuple(ids)


async def _require_private(message: Message, state: FSMContext | None = None) -> bool:
    if is_private_message(message):
        return True
    if state is not None:
        await state.clear()
    await message.answer(PRIVATE_CHAT_REQUIRED)
    return False


async def _require_private_callback(query: CallbackQuery, state: FSMContext | None = None) -> bool:
    if query.message is not None and is_private_message(query.message):
        return True
    if state is not None:
        await state.clear()
    await query.answer(PRIVATE_CHAT_REQUIRED, show_alert=True)
    return False


def _parse_wallet_id(value: str | None, prefix: str) -> UUID | None:
    if not value or not value.startswith(prefix):
        return None
    try:
        return UUID(value.removeprefix(prefix))
    except ValueError:
        return None


async def _start_registration(message: Message, state: FSMContext) -> None:
    if not await _require_private(message, state):
        return
    if authenticated_telegram_user_id(message) is None:
        await message.answer(WALLET_RETRY_MESSAGE)
        return
    await state.clear()
    await state.set_state(WalletRegistrationState.network)
    await message.answer("اختر شبكة المحفظة المدعومة.", reply_markup=_network_keyboard())


async def _render_wallet_list(message: Message, composition: CustomerComposition) -> None:
    if not await _require_private(message):
        return
    user_id = authenticated_telegram_user_id(message)
    if user_id is None:
        await message.answer(WALLET_RETRY_MESSAGE)
        return
    response = await composition.wallets.list(user_id)
    if not response.ok:
        await message.answer(response.text or WALLET_RETRY_MESSAGE)
        return
    await message.answer(response.text, reply_markup=wallet_listing_markup(response.text))


def build_customer_wallets_router(composition: CustomerComposition) -> Router:
    """Build the bounded customer-wallet Telegram transport flow."""

    router = Router(name="customer-wallets")

    @router.message(Command("wallets"))
    async def list_wallets(message: Message) -> None:
        await _render_wallet_list(message, composition)

    @router.callback_query(F.data == WALLET_LIST_CALLBACK)
    async def list_wallets_callback(query: CallbackQuery) -> None:
        if not await _require_private_callback(query):
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المستخدم.", show_alert=True)
            return
        response = await composition.wallets.list(user_id)
        await query.answer()
        if query.message is None:
            return
        if not response.ok:
            await query.message.edit_text(response.text or WALLET_RETRY_MESSAGE)
            return
        await query.message.edit_text(response.text, reply_markup=wallet_listing_markup(response.text))

    @router.message(Command("wallet_add"))
    async def begin_registration(message: Message, state: FSMContext) -> None:
        await _start_registration(message, state)

    @router.callback_query(F.data == WALLET_ADD_CALLBACK)
    async def begin_registration_callback(query: CallbackQuery, state: FSMContext) -> None:
        if not await _require_private_callback(query, state):
            return
        if authenticated_telegram_user_id(query) is None:
            await query.answer("تعذر التحقق من هوية المستخدم.", show_alert=True)
            return
        await state.clear()
        await state.set_state(WalletRegistrationState.network)
        await query.answer()
        if query.message is not None:
            await query.message.edit_text("اختر شبكة المحفظة المدعومة.", reply_markup=_network_keyboard())

    @router.callback_query(WalletRegistrationState.network, F.data.startswith("wallet:network:"))
    async def select_network(query: CallbackQuery, state: FSMContext) -> None:
        if not await _require_private_callback(query, state):
            return
        network = (query.data or "").removeprefix("wallet:network:")
        if network not in SUPPORTED_WALLET_NETWORKS:
            await query.answer("هذه الشبكة غير مدعومة.", show_alert=True)
            return
        await state.update_data(network=network)
        await state.set_state(WalletRegistrationState.address)
        await query.answer()
        if query.message is not None:
            await query.message.edit_text(
                f"أرسل عنوان الاستلام على شبكة {network}.",
                reply_markup=_cancel_keyboard(),
            )

    @router.message(WalletRegistrationState.address, F.text)
    async def receive_address(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        await state.update_data(address=message.text or "")
        await state.set_state(WalletRegistrationState.label)
        await message.answer("أرسل اسمًا قصيرًا للمحفظة.", reply_markup=_cancel_keyboard())

    @router.message(WalletRegistrationState.address)
    async def require_address(message: Message, state: FSMContext) -> None:
        if await _require_private(message, state):
            await message.answer("أرسل عنوان المحفظة كنص، أو استخدم /cancel للإلغاء.")

    @router.message(WalletRegistrationState.label, F.text)
    async def receive_label(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        await state.update_data(label=message.text or "")
        await state.set_state(WalletRegistrationState.qr)
        await message.answer(
            "أرسل صورة QR للمحفظة، وضع العنوان الذي يمثله QR في وصف الصورة (caption).",
            reply_markup=_cancel_keyboard(),
        )

    @router.message(WalletRegistrationState.label)
    async def require_label(message: Message, state: FSMContext) -> None:
        if await _require_private(message, state):
            await message.answer("أرسل اسم المحفظة كنص، أو استخدم /cancel للإلغاء.")

    @router.message(WalletRegistrationState.qr, F.photo)
    async def receive_qr(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        user_id = authenticated_telegram_user_id(message)
        photo = message.photo[-1] if message.photo else None
        values = await state.get_data()
        if user_id is None or photo is None:
            await state.clear()
            await message.answer(WALLET_RETRY_MESSAGE)
            return
        response = await composition.wallets.register(
            TelegramWalletRegistrationInput(
                user_id=user_id,
                address=str(values.get("address", "")),
                network=str(values.get("network", "")),
                qr_address=message.caption or "",
                qr_image_file_id=photo.file_id,
                label=str(values.get("label", "")),
            )
        )
        await state.clear()
        if response.ok:
            await message.answer(response.text, reply_markup=wallet_management_markup())
            return
        await message.answer(
            f"{response.text or WalletMessages.INVALID} ابدأ من جديد باستخدام /wallet_add."
        )

    @router.message(WalletRegistrationState.qr)
    async def require_qr(message: Message, state: FSMContext) -> None:
        if await _require_private(message, state):
            await message.answer(
                "أرسل QR كصورة مع العنوان في وصف الصورة، أو استخدم /cancel للإلغاء."
            )

    @router.message(WalletRegistrationState.network, Command("cancel"))
    @router.message(WalletRegistrationState.address, Command("cancel"))
    @router.message(WalletRegistrationState.label, Command("cancel"))
    @router.message(WalletRegistrationState.qr, Command("cancel"))
    async def cancel_registration(message: Message, state: FSMContext) -> None:
        await state.clear()
        if is_private_message(message):
            await message.answer(WALLET_CANCELLED_MESSAGE, reply_markup=wallet_management_markup())

    @router.callback_query(F.data == WALLET_CANCEL_CALLBACK)
    async def cancel_registration_callback(query: CallbackQuery, state: FSMContext) -> None:
        if not await _require_private_callback(query, state):
            return
        await state.clear()
        await query.answer("تم الإلغاء.")
        if query.message is not None:
            await query.message.edit_text(WALLET_CANCELLED_MESSAGE, reply_markup=wallet_management_markup())

    @router.callback_query(F.data.regexp(r"^wallet:disable:[0-9a-fA-F-]{36}$"))
    async def request_disable(query: CallbackQuery) -> None:
        if not await _require_private_callback(query):
            return
        user_id = authenticated_telegram_user_id(query)
        wallet_id = _parse_wallet_id(query.data, WALLET_DISABLE_CALLBACK_PREFIX)
        if user_id is None or wallet_id is None:
            await query.answer("طلب تعطيل غير صالح.", show_alert=True)
            return
        response = await composition.wallets.disable(TelegramWalletInput(user_id, wallet_id, False))
        await query.answer()
        if query.message is None:
            return
        if not response.ok:
            if response.text == WalletMessages.CONFIRMATION_REQUIRED or response.text:
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="تأكيد تعطيل المحفظة",
                                callback_data=f"{WALLET_DISABLE_CONFIRM_PREFIX}{wallet_id}",
                            )
                        ],
                        [InlineKeyboardButton(text="إلغاء", callback_data=WALLET_CANCEL_CALLBACK)],
                    ]
                )
                await query.message.edit_text(response.text, reply_markup=markup)
                return
        await query.message.edit_text(response.text or WALLET_RETRY_MESSAGE, reply_markup=wallet_management_markup())

    @router.callback_query(F.data.regexp(r"^wallet:disable:confirm:[0-9a-fA-F-]{36}$"))
    async def confirm_disable(query: CallbackQuery) -> None:
        if not await _require_private_callback(query):
            return
        user_id = authenticated_telegram_user_id(query)
        wallet_id = _parse_wallet_id(query.data, WALLET_DISABLE_CONFIRM_PREFIX)
        if user_id is None or wallet_id is None:
            await query.answer("طلب تعطيل غير صالح.", show_alert=True)
            return
        response = await composition.wallets.disable(TelegramWalletInput(user_id, wallet_id, True))
        await query.answer()
        if query.message is not None:
            await query.message.edit_text(response.text or WALLET_RETRY_MESSAGE, reply_markup=wallet_management_markup())

    return router
