from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.composition_root import CustomerComposition
from app.runtime.telegram.contracts import TelegramOrderInput
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

PRIVATE_CHAT_REQUIRED = "حفاظًا على خصوصيتك، أكمل إنشاء الطلب في محادثة خاصة مع البوت."
ORDER_CANCELLED = "تم إلغاء إنشاء الطلب."
ORDER_RETRY_MESSAGE = "تعذر إنشاء الطلب حاليًا. حاول مرة أخرى."
WALLETS_RETRY_MESSAGE = "تعذر تحميل المحافظ الموثقة. حاول مرة أخرى."
WALLET_CALLBACK_PREFIX = "purchase:wallet:"
CURRENCY_CALLBACKS = {"purchase:currency:usd": "USD", "purchase:currency:new_syp": "NEW.SYP"}
CONFIRM_CALLBACK = "purchase:confirm"
CANCEL_CALLBACK = "purchase:cancel"

class PurchaseOrderState(StatesGroup):
    amount = State()
    wallet = State()
    currency = State()
    confirmation = State()

def _cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="إلغاء", callback_data=CANCEL_CALLBACK)]])

def _currency_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="USD", callback_data="purchase:currency:usd"),
        InlineKeyboardButton(text="NEW.SYP", callback_data="purchase:currency:new_syp"),
    ], [InlineKeyboardButton(text="إلغاء", callback_data=CANCEL_CALLBACK)]])

def _wallet_markup(wallets: tuple[object, ...]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for wallet in wallets:
        wallet_id = getattr(wallet, "wallet_id", None)
        network = getattr(wallet, "network", None)
        address = str(getattr(wallet, "address", ""))
        if not isinstance(wallet_id, UUID) or not address:
            continue
        network_code = getattr(network, "value", str(network))
        short_address = address if len(address) <= 14 else f"{address[:8]}…{address[-5:]}"
        buttons.append([InlineKeyboardButton(text=f"{network_code} · {short_address}", callback_data=f"{WALLET_CALLBACK_PREFIX}{wallet_id}")])
    buttons.append([InlineKeyboardButton(text="إلغاء", callback_data=CANCEL_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def parse_positive_amount(raw: str | None) -> Decimal | None:
    try:
        amount = Decimal((raw or "").strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount > 0 else None

def _build_input(data: dict[str, object], user_id: int) -> TelegramOrderInput:
    return TelegramOrderInput.from_values(
        user_id=user_id,
        wallet_id=str(data.get("wallet_id", "")),
        network_code=str(data.get("network_code", "")),
        requested_amount=str(data.get("requested_amount", "")),
        payment_currency=str(data.get("payment_currency", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
    )

def _quote_fingerprint(quote: object) -> tuple[str, ...]:
    financials = quote.financials
    rate = quote.exchange_rate_snapshot
    return (
        str(financials.requested_amount), str(financials.fee_percent), str(financials.fee_amount),
        str(financials.net_usdt_amount), str(financials.payment_currency), str(financials.exchange_rate),
        str(financials.local_amount), str(financials.rounding_policy_version),
        str(quote.fee_policy_snapshot.version), str(rate.version if rate else ""),
        str(rate.rate if rate else ""),
    )

def render_confirmation(data: dict[str, object], quote: object) -> str:
    financials = quote.financials
    rate = quote.exchange_rate_snapshot
    lines = [
        "راجع عرض السعر قبل تأكيد الطلب:",
        f"• المبلغ المطلوب: {financials.requested_amount} USDT",
        f"• رسوم الخدمة: {financials.fee_amount} USDT ({financials.fee_percent}%)",
        f"• صافي USDT: {financials.net_usdt_amount} USDT",
        f"• عملة الدفع: {financials.payment_currency}",
        f"• المبلغ المطلوب دفعه: {financials.local_amount} {financials.payment_currency}",
    ]
    if rate is not None:
        lines.append(f"• سعر الصرف: {rate.rate} {financials.payment_currency}/USDT")
    lines.extend(["", "عرض السعر صالح لمدة 10 دقائق تقريبًا، ويُعاد التحقق منه لحظة التأكيد."])
    return "\n".join(lines)

def render_created_order(order_text: str) -> str:
    return f"{order_text}\n\nاحتفظ برقم الطلب. لا ترسل أي مبلغ إلا وفق تعليمات الدفع الرسمية للطلب."

async def _require_private(message: Message, state: FSMContext) -> bool:
    if is_private_message(message):
        return True
    await state.clear()
    await message.answer(PRIVATE_CHAT_REQUIRED)
    return False

async def _load_wallets(message: Message, state: FSMContext, composition: CustomerComposition, user_id: int) -> None:
    response = await composition.wallets.list_available_for_order(user_id)
    if not response.ok:
        await message.answer(WALLETS_RETRY_MESSAGE, reply_markup=_cancel_markup())
        return
    if not response.wallets:
        await state.clear()
        await message.answer("لا توجد محافظ موثقة متاحة. أضف محفظة موثقة أولاً.", reply_markup=_cancel_markup())
        return
    await state.set_state(PurchaseOrderState.wallet)
    await message.answer("اختر المحفظة الموثقة التي سيُرسل إليها USDT.", reply_markup=_wallet_markup(response.wallets))

def build_customer_purchase_order_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer-purchase-order")

    @router.message(Command("buy", "purchase"))
    async def begin(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        if authenticated_telegram_user_id(message) is None:
            await message.answer(ORDER_RETRY_MESSAGE)
            return
        await state.clear()
        await state.update_data(idempotency_key=f"telegram-order:{uuid4().hex}")
        await state.set_state(PurchaseOrderState.amount)
        await message.answer("أرسل مبلغ USDT الذي تريد شراءه.", reply_markup=_cancel_markup())

    @router.message(PurchaseOrderState.amount, F.text)
    async def receive_amount(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        user_id = authenticated_telegram_user_id(message)
        amount = parse_positive_amount(message.text)
        if user_id is None:
            await message.answer(ORDER_RETRY_MESSAGE)
        elif amount is None:
            await message.answer("أرسل مبلغًا موجبًا وصالحًا فقط.", reply_markup=_cancel_markup())
        else:
            await state.update_data(requested_amount=str(amount))
            await _load_wallets(message, state, composition, user_id)

    @router.callback_query(PurchaseOrderState.wallet, F.data.startswith(WALLET_CALLBACK_PREFIX))
    async def select_wallet(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not await _require_private(query.message, state):
            await query.answer()
            return
        user_id = authenticated_telegram_user_id(query)
        raw_wallet_id = (query.data or "").removeprefix(WALLET_CALLBACK_PREFIX)
        try:
            selected_wallet_id = UUID(raw_wallet_id)
        except ValueError:
            await query.answer("المحفظة غير صالحة.", show_alert=True)
            return
        if user_id is None:
            await query.answer(ORDER_RETRY_MESSAGE, show_alert=True)
            return
        response = await composition.wallets.list_available_for_order(user_id)
        wallet = next((item for item in response.wallets if getattr(item, "wallet_id", None) == selected_wallet_id), None)
        if not response.ok or wallet is None:
            await query.answer("المحفظة لم تعد متاحة. اختر محفظة أخرى.", show_alert=True)
            return
        network = getattr(wallet, "network", None)
        network_code = getattr(network, "value", None)
        if not isinstance(network_code, str) or not network_code:
            await query.answer(ORDER_RETRY_MESSAGE, show_alert=True)
            return
        await state.update_data(wallet_id=str(selected_wallet_id), network_code=network_code)
        await state.set_state(PurchaseOrderState.currency)
        await query.answer()
        await query.message.answer("اختر عملة الدفع.", reply_markup=_currency_markup())

    @router.callback_query(PurchaseOrderState.currency, F.data.in_(CURRENCY_CALLBACKS))
    async def select_currency(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not await _require_private(query.message, state):
            await query.answer()
            return
        currency = CURRENCY_CALLBACKS.get(query.data or "")
        if currency is None:
            await query.answer("عملة غير صالحة.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer(ORDER_RETRY_MESSAGE, show_alert=True)
            return
        await state.update_data(payment_currency=currency)
        data = await state.get_data()
        try:
            request = _build_input(data, user_id)
        except ValueError:
            await state.clear()
            await query.answer("بيانات الطلب غير مكتملة. ابدأ من جديد.", show_alert=True)
            return
        preview = await composition.order_creation.preview(request)
        if not preview.ok or preview.quote is None:
            await query.answer(preview.text or ORDER_RETRY_MESSAGE, show_alert=True)
            return
        await state.update_data(quote_fingerprint=_quote_fingerprint(preview.quote))
        await state.set_state(PurchaseOrderState.confirmation)
        await query.answer()
        await query.message.answer(render_confirmation(data, preview.quote), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="تأكيد الطلب", callback_data=CONFIRM_CALLBACK)],
            [InlineKeyboardButton(text="إلغاء", callback_data=CANCEL_CALLBACK)],
        ]))

    @router.callback_query(PurchaseOrderState.confirmation, F.data == CONFIRM_CALLBACK)
    async def confirm(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not await _require_private(query.message, state):
            await query.answer()
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer(ORDER_RETRY_MESSAGE, show_alert=True)
            return
        data = await state.get_data()
        try:
            request = _build_input(data, user_id)
        except ValueError:
            await state.clear()
            await query.answer("بيانات الطلب غير مكتملة. ابدأ من جديد.", show_alert=True)
            return
        preview = await composition.order_creation.preview(request)
        if not preview.ok or preview.quote is None:
            await query.answer(preview.text or ORDER_RETRY_MESSAGE, show_alert=True)
            return
        if tuple(data.get("quote_fingerprint", ())) != _quote_fingerprint(preview.quote):
            await state.update_data(quote_fingerprint=_quote_fingerprint(preview.quote))
            await query.answer("تغير السعر أو الرسوم. راجع العرض المحدث ثم أكد مرة أخرى.", show_alert=True)
            await query.message.answer(render_confirmation(data, preview.quote), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="تأكيد الطلب", callback_data=CONFIRM_CALLBACK)],
                [InlineKeyboardButton(text="إلغاء", callback_data=CANCEL_CALLBACK)],
            ]))
            return
        response = await composition.order_creation.handle(request)
        await query.answer()
        if not response.ok:
            await query.message.answer(response.text or ORDER_RETRY_MESSAGE)
            return
        await state.clear()
        await query.message.answer(render_created_order(response.text))

    @router.callback_query(F.data == CANCEL_CALLBACK)
    async def cancel_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await query.answer()
        if query.message is not None:
            await query.message.answer(ORDER_CANCELLED)

    @router.message(Command("cancel"))
    async def cancel_command(message: Message, state: FSMContext) -> None:
        if not await _require_private(message, state):
            return
        await state.clear()
        await message.answer(ORDER_CANCELLED)

    return router
