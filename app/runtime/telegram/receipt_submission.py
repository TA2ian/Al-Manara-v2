from __future__ import annotations

import asyncio
from io import BytesIO
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.application.customer_order_details import GetCustomerOrderDetailsCommand
from app.application.submit_customer_receipt import SubmitCustomerReceiptCommand
from app.composition_root import CustomerComposition
from app.domain.receipt_attempt import ReceiptAttemptStatus, ReceiptInputType, SUPPORTED_RECEIPT_MIME_TYPES, MAX_TRANSACTION_REFERENCE_LENGTH
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
RECEIPT_DOWNLOAD_TIMEOUT_SECONDS = 15
RECEIPT_CALLBACK = "orders:receipt:"
ORDER_CODE_MAX_LENGTH = 100


class CustomerReceiptState(StatesGroup):
    awaiting_image = State()
    awaiting_text = State()


class ReceiptMessages:
    PROMPT = (
        "أرسل رقم عملية شام كاش كنص، أو أرسل صورة إيصال "
        "المسموح: JPG أو PNG أو WEBP، وبحد أقصى 5 MB."
    )
    INVALID = "بيانات الإيصال غير صالحة."
    UNSUPPORTED_FORMAT = "يرجى إرسال صورة الإيصال بصيغة JPG أو PNG أو WEBP."
    TOO_LARGE = "حجم الإيصال يتجاوز الحد المسموح وهو 5 MB."
    ACCEPTED = "تم استلام الإيصال وإدخاله في قائمة المراجعة. الموافقة المالية النهائية يحددها الأدمن يدويًا."
    FAILED = "تعذر معالجة الإيصال. أرسل صورة واضحة وصالحة وحاول مرة أخرى."
    ERROR = "تعذر معالجة الإيصال حاليًا. حاول مرة أخرى."


async def _download_receipt(message: Message) -> tuple[str, bytes]:
    if message.photo:
        photo = message.photo[-1]
        if photo.file_size is not None and photo.file_size > MAX_RECEIPT_BYTES:
            raise ValueError("receipt image exceeds size limit")
        file_id = photo.file_id
        declared_mime = "image/jpeg"
    elif message.document is not None:
        document = message.document
        declared_mime = (document.mime_type or "").strip().lower()
        if declared_mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt image type")
        if document.file_size is not None and document.file_size > MAX_RECEIPT_BYTES:
            raise ValueError("receipt image exceeds size limit")
        file_id = document.file_id
    else:
        raise ValueError("receipt image is required")

    telegram_file = await asyncio.wait_for(
        message.bot.get_file(file_id),
        timeout=RECEIPT_DOWNLOAD_TIMEOUT_SECONDS,
    )
    if telegram_file.file_size is not None and telegram_file.file_size > MAX_RECEIPT_BYTES:
        raise ValueError("receipt image exceeds size limit")
    if not telegram_file.file_path:
        raise RuntimeError("telegram file path is unavailable")

    downloaded = await asyncio.wait_for(
        message.bot.download_file(
            telegram_file.file_path,
            destination=BytesIO(),
            timeout=RECEIPT_DOWNLOAD_TIMEOUT_SECONDS,
            chunk_size=65536,
            seek=True,
        ),
        timeout=RECEIPT_DOWNLOAD_TIMEOUT_SECONDS + 2,
    )
    if downloaded is None:
        raise RuntimeError("telegram download returned no data")
    content = downloaded.getvalue()
    if len(content) > MAX_RECEIPT_BYTES:
        raise ValueError("receipt image exceeds size limit")
    return declared_mime, content


def build_customer_receipt_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer-receipt")

    @router.callback_query(F.data.startswith(RECEIPT_CALLBACK))
    async def begin_receipt(query: CallbackQuery, state: FSMContext) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("حفاظًا على الخصوصية، أرسل الإيصال في المحادثة الخاصة.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        public_code = (query.data or "")[len(RECEIPT_CALLBACK):].strip()
        if user_id is None or not 1 <= len(public_code) <= ORDER_CODE_MAX_LENGTH:
            await query.answer(ReceiptMessages.INVALID, show_alert=True)
            return
        try:
            order = await composition.order_details.get(
                GetCustomerOrderDetailsCommand(
                    customer_telegram_user_id=user_id,
                    public_order_code=public_code,
                )
            )
        except Exception:
            await query.answer(ReceiptMessages.ERROR, show_alert=True)
            return
        if order is None:
            await query.answer("الطلب غير موجود أو لا ينتمي إلى حسابك.", show_alert=True)
            return
        if order.status.value != "PENDING_PAYMENT":
            await query.answer("هذا الطلب لا يستقبل إيصالات في حالته الحالية.", show_alert=True)
            return
        await state.clear()
        await state.update_data(receipt_order_id=str(order.internal_order_id), receipt_public_code=order.public_order_code)
        await state.set_state(CustomerReceiptState.awaiting_image)
        await query.answer()
        await query.message.answer(ReceiptMessages.PROMPT)

    @router.message(CustomerReceiptState.awaiting_image, F.text)
    async def receive_text(message: Message, state: FSMContext) -> None:
        if not is_private_message(message):
            await state.clear()
            return
        user_id = authenticated_telegram_user_id(message)
        data = await state.get_data()
        try:
            order_id = UUID(str(data["receipt_order_id"]))
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer(ReceiptMessages.INVALID)
            return
        reference = " ".join((message.text or "").split())
        if user_id is None or not reference or len(reference) > MAX_TRANSACTION_REFERENCE_LENGTH:
            await message.answer("رقم العملية غير صالح.")
            return
        try:
            result = await composition.customer_receipt.submit(SubmitCustomerReceiptCommand(
                order_id=order_id,
                telegram_user_id=user_id,
                idempotency_key=f"receipt:{user_id}:{order_id}:{message.message_id}",
                input_type=ReceiptInputType.TEXT,
                transaction_reference=reference,
            ))
        except ValueError:
            await message.answer(ReceiptMessages.FAILED)
            return
        except Exception:
            await message.answer(ReceiptMessages.ERROR)
            return
        if result.status not in {ReceiptAttemptStatus.SUBMITTED, ReceiptAttemptStatus.VERIFIED}:
            await message.answer(ReceiptMessages.ERROR)
            return
        await state.clear()
        await message.answer(f"{ReceiptMessages.ACCEPTED}\nرقم العملية: {reference}")

    @router.message(CustomerReceiptState.awaiting_image, F.photo)
    async def receive_photo(message: Message, state: FSMContext) -> None:
        await _receive_image(message, state, composition, "image/jpeg")

    @router.message(CustomerReceiptState.awaiting_image, F.document)
    async def receive_document(message: Message, state: FSMContext) -> None:
        mime = (message.document.mime_type or "").strip().lower() if message.document else ""
        if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            await message.answer(ReceiptMessages.UNSUPPORTED_FORMAT)
            return
        await _receive_image(message, state, composition, mime)

    @router.message(CustomerReceiptState.awaiting_image)
    async def reject_non_image(message: Message) -> None:
        await message.answer(ReceiptMessages.UNSUPPORTED_FORMAT)

    return router


async def _receive_image(message: Message, state: FSMContext, composition: CustomerComposition, declared_mime: str) -> None:
    if not is_private_message(message):
        await state.clear()
        await message.answer("حفاظًا على الخصوصية، أرسل الإيصال في المحادثة الخاصة.")
        return
    user_id = authenticated_telegram_user_id(message)
    data = await state.get_data()
    raw_order_id = data.get("receipt_order_id")
    public_code = str(data.get("receipt_public_code", "")).strip()
    try:
        order_id = UUID(str(raw_order_id))
    except (TypeError, ValueError):
        await state.clear()
        await message.answer(ReceiptMessages.INVALID)
        return
    if user_id is None or not public_code:
        await state.clear()
        await message.answer(ReceiptMessages.INVALID)
        return

    try:
        actual_declared_mime, content = await _download_receipt(message)
        # For Telegram photos the declared type is fixed to JPEG; for documents
        # use Telegram's declaration but validate the actual bytes in the domain.
        if actual_declared_mime != declared_mime:
            declared_mime = actual_declared_mime
        result = await composition.customer_receipt.submit(
            SubmitCustomerReceiptCommand(
                order_id=order_id,
                telegram_user_id=user_id,
                telegram_file_id=(message.photo[-1].file_id if message.photo else message.document.file_id),
                declared_mime_type=declared_mime,
                idempotency_key=f"receipt:{user_id}:{order_id}:{message.message_id}",
            ),
            content,
        )
    except ValueError as exc:
        if "size limit" in str(exc).lower():
            await message.answer(ReceiptMessages.TOO_LARGE)
        else:
            await message.answer(ReceiptMessages.FAILED)
        return
    except Exception:
        await message.answer(ReceiptMessages.ERROR)
        return

    if result.status not in {ReceiptAttemptStatus.SUBMITTED, ReceiptAttemptStatus.VERIFIED}:
        await message.answer(ReceiptMessages.ERROR)
        return
    await state.clear()
    await message.answer(f"{ReceiptMessages.ACCEPTED}\nرقم الطلب: {public_code}")


# Backward-compatible framework-neutral DTOs retained for application tests.
from dataclasses import dataclass
from typing import Protocol
from app.application.submit_receipt import SubmitReceiptCommand
from app.domain.receipt_attempt import ReceiptInputType


@dataclass(frozen=True, slots=True)
class TelegramReceiptInput:
    user_id: int
    order_id: UUID
    input_type: ReceiptInputType
    idempotency_key: str
    transaction_reference: str | None = None
    telegram_file_id: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramReceiptResponse:
    ok: bool
    text: str


class ReceiptSubmissionService(Protocol):
    async def submit(self, command: SubmitReceiptCommand): ...


@dataclass(frozen=True, slots=True)
class TelegramReceiptHandler:
    submission: ReceiptSubmissionService

    async def submit(self, data: TelegramReceiptInput) -> TelegramReceiptResponse:
        if data.user_id <= 0 or not isinstance(data.order_id, UUID):
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        if data.input_type is not ReceiptInputType.IMAGE:
            return TelegramReceiptResponse(False, ReceiptMessages.UNSUPPORTED_FORMAT)
        if not data.idempotency_key.strip():
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        telegram_file_id = data.telegram_file_id.strip() if data.telegram_file_id is not None else None
        mime_type = data.mime_type.strip().lower() if data.mime_type is not None else None
        if not telegram_file_id or mime_type not in SUPPORTED_RECEIPT_MIME_TYPES:
            return TelegramReceiptResponse(False, ReceiptMessages.UNSUPPORTED_FORMAT)
        if data.transaction_reference is not None:
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        try:
            await self.submission.submit(
                SubmitReceiptCommand(
                    order_id=data.order_id,
                    telegram_user_id=data.user_id,
                    input_type=ReceiptInputType.IMAGE,
                    transaction_reference=None,
                    telegram_file_id=telegram_file_id,
                    mime_type=mime_type,
                    idempotency_key=data.idempotency_key.strip(),
                )
            )
        except ValueError:
            return TelegramReceiptResponse(False, ReceiptMessages.FAILED)
        except Exception:
            return TelegramReceiptResponse(False, ReceiptMessages.ERROR)
        return TelegramReceiptResponse(True, ReceiptMessages.ACCEPTED)
