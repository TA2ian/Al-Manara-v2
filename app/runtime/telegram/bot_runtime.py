"""Production aiogram polling runtime for the approved V2 customer routes."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    ErrorEvent,
)
from supabase import create_client

from app.composition_root import build_customer_composition
from app.runtime.telegram.router import build_customer_router
from app.composition_root import (

POLLING_UPDATE_TYPES = ("message", "callback_query")
LEASE_DURATION_SECONDS = 30
LEASE_RENEWAL_INTERVAL_SECONDS = 10
LEASE_RPC_TIMEOUT_SECONDS = 5
LOGGER = logging.getLogger(__name__)
from app.runtime.telegram.admin_customer_identity import TelegramAdminCustomerIdentityHandler


@dataclass(frozen=True, slots=True)
class TelegramBotSettings:
    token: str
    supabase_url: str
    supabase_service_role_key: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "TelegramBotSettings":
        values = environment if environment is not None else os.environ
        required = {
            "TELEGRAM_BOT_TOKEN": values.get("TELEGRAM_BOT_TOKEN", "").strip(),
            "SUPABASE_URL": values.get("SUPABASE_URL", "").strip(),
            "SUPABASE_SERVICE_ROLE_KEY": values.get(
                "SUPABASE_SERVICE_ROLE_KEY", ""
            ).strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing required bot configuration: {', '.join(missing)}"
            )
        return cls(
            token=required["TELEGRAM_BOT_TOKEN"],
            supabase_url=required["SUPABASE_URL"],
            supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        )


class SinglePollerLock:
    """An OS-level exclusive lock that prevents duplicate pollers in one Replit."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(tempfile.gettempdir()) / "al-manara-v2-telegram.lock"
        self._handle = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class SharedPollerLease(Protocol):
    """A renewable lease that coordinates pollers across independent hosts."""

    async def acquire(self) -> bool: ...

    async def renew(self) -> bool: ...

    async def release(self) -> bool: ...


class SharedPollerLeaseError(RuntimeError):
    """The shared lease store could not confirm ownership."""


class SharedPollerLeaseUnavailable(RuntimeError):
    """Another healthy host currently owns the customer poller lease."""


class SupabaseSharedPollerLease:
    """Supabase RPC adapter for the customer Telegram polling lease."""

    def __init__(
        self,
        client: Any,
        *,
        owner_id: UUID | None = None,
        lease_seconds: int = LEASE_DURATION_SECONDS,
        rpc_timeout_seconds: float = LEASE_RPC_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._owner_id = owner_id or uuid4()
        self._lease_seconds = lease_seconds
        self._rpc_timeout_seconds = rpc_timeout_seconds

    async def acquire(self) -> bool:
        return await self._call("acquire_telegram_poller_lease", "acquired")

    async def renew(self) -> bool:
        return await self._call("renew_telegram_poller_lease", "renewed")

    async def release(self) -> bool:
        return await self._call("release_telegram_poller_lease", "released")

    async def _call(self, function_name: str, result_name: str) -> bool:
        params: dict[str, object] = {"p_owner_id": str(self._owner_id)}
        if function_name != "release_telegram_poller_lease":
            params["p_lease_seconds"] = self._lease_seconds
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._client.rpc(function_name, params).execute),
                timeout=self._rpc_timeout_seconds,
            )
        except Exception as exc:
            raise SharedPollerLeaseError("shared poller lease RPC failed") from exc
        if getattr(response, "error", None):
            raise SharedPollerLeaseError("shared poller lease RPC returned an error")
        data = getattr(response, "data", None)
        if (
            not isinstance(data, list)
            or len(data) != 1
            or not isinstance(data[0], dict)
            or not isinstance(data[0].get(result_name), bool)
        ):
            raise SharedPollerLeaseError("shared poller lease RPC returned invalid data")
        return data[0][result_name]


def build_shared_poller_lease(settings: TelegramBotSettings) -> SharedPollerLease:
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return SupabaseSharedPollerLease(client)


async def log_telegram_error(event: ErrorEvent) -> bool:
    """Record a safe operational event without rendering SDK exception details."""

    del event
    LOGGER.error("Unhandled Telegram update error.")
    return True


def build_telegram_runtime(settings: TelegramBotSettings) -> tuple[Bot, Dispatcher]:
    """Build the aiogram transport and V2 composition without executing requests."""

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_identity_review_router(build_identity_review_handler(client)))
    dispatcher.include_router(build_customer_router(build_customer_composition(client)))
    dispatcher.errors.register(log_telegram_error)
    return Bot(token=settings.token), dispatcher


async def _renew_lease_until_stopped(
    lease: SharedPollerLease,
    dispatcher: Dispatcher,
    renewal_interval_seconds: float,
    renewal_timeout_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(renewal_interval_seconds)
        try:
            renewed = await asyncio.wait_for(lease.renew(), timeout=renewal_timeout_seconds)
        except (TimeoutError, SharedPollerLeaseError):
            renewed = False
        if not renewed:
            LOGGER.error(
                "Shared Telegram poller lease was lost; stopping before processing more updates."
            )
            await dispatcher.stop_polling()
            return


async def run_polling(
    settings: TelegramBotSettings,
    lease: SharedPollerLease | None = None,
    *,
    renewal_interval_seconds: float = LEASE_RENEWAL_INTERVAL_SECONDS,
    renewal_timeout_seconds: float = LEASE_RPC_TIMEOUT_SECONDS,
) -> None:
    """Acquire the cross-host lease, poll, and surrender it on clean shutdown."""
    if renewal_interval_seconds <= 0 or renewal_timeout_seconds <= 0:
        raise ValueError("lease renewal interval and timeout must be positive")
    if renewal_interval_seconds + renewal_timeout_seconds >= LEASE_DURATION_SECONDS:
        raise ValueError("lease renewal must fail before the lease can expire")
    shared_lease = lease or build_shared_poller_lease(settings)
    if not await shared_lease.acquire():
        raise SharedPollerLeaseUnavailable("another host owns the Telegram poller lease")

    bot: Bot | None = None
    renew_task: asyncio.Task[None] | None = None
    try:
        bot, dispatcher = build_telegram_runtime(settings)
        renew_task = asyncio.create_task(
            _renew_lease_until_stopped(
                shared_lease,
                dispatcher,
                renewal_interval_seconds,
                renewal_timeout_seconds,
            )
        )
        # Polling and webhooks are mutually exclusive. Preserve pending updates so
        # V2 idempotency rules, rather than startup policy, own replay behavior.
        await bot.delete_webhook(drop_pending_updates=False)
        # Command filters validate an addressed command (for example,
        # /orders@OurBot) through Bot.me(). Cache the startup identity so
        # group-chat commands do not need a second identity request later.
        identity = await bot.get_me()
        bot._me = identity
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="عرض المساعدة"),
                BotCommand(command="verify", description="إرسال بيانات التحقق"),
                BotCommand(command="orders", description="عرض طلباتك"),
                BotCommand(command="identity_pending", description="مراجعة طلبات التحقق"),
            ]
        )
        LOGGER.info("Telegram polling transport is ready for bot id %s.", identity.id)
        await dispatcher.start_polling(bot, allowed_updates=POLLING_UPDATE_TYPES)
    finally:
        if renew_task is not None:
            renew_task.cancel()
            await asyncio.gather(renew_task, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        try:
            await shared_lease.release()
        except SharedPollerLeaseError:
            # A failed clean release is safe: the database expiry prevents a
            # permanently stranded lease without risking a second poller now.
            LOGGER.error("Unable to release the shared Telegram poller lease.")


def main(lock: SinglePollerLock | None = None) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    poller_lock = lock or SinglePollerLock()
    if not poller_lock.acquire():
        LOGGER.error("Telegram bot is already running in this Replit; refusing a second poller.")
        raise SystemExit(1)
    try:
        LOGGER.info("Starting Telegram polling service.")
        asyncio.run(run_polling(TelegramBotSettings.from_environment()))
    except Exception:
        # SDK exception details may contain request configuration or secrets.
        LOGGER.error("Telegram bot stopped because startup or polling failed.")
        raise SystemExit(1) from None
    finally:
        poller_lock.release()

class IdentityReviewState(StatesGroup):
    rejection_reason = State()

def parse_identity_review_callback(callback_data: str | None) -> tuple[str, UUID] | None:
    match = IDENTITY_REVIEW_CALLBACK.fullmatch(callback_data or "")
    if match is None:
        return None
    try:
        return match.group(1), UUID(match.group(2))
    except ValueError:
        return None

def _identity_review_markup(submission_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="اعتماد", callback_data=f"identity:approve:{submission_id}"
                ),
                InlineKeyboardButton(
                    text="رفض", callback_data=f"identity:reject:{submission_id}"
                ),
            ]
        ]
    )

def _identity_review_caption(submission: Any) -> str:
    return (
        "طلب تحقق بانتظار المراجعة\n"
        f"العميل: {submission.customer_telegram_user_id}\n"
        f"الاسم: {submission.full_name}\n"
        f"حساب Sham Cash: {submission.shamcash_account}\n"
        f"قُدّم: {submission.submitted_at.isoformat()}"
    )

def build_identity_review_router(handler: TelegramAdminCustomerIdentityHandler) -> Router:
    """Routes identity review through a private Telegram conversation only."""

    router = Router(name="primary-admin-customer-identity")

    @router.message(Command("identity_pending"))
    async def show_pending_identity_submissions(message: Message) -> None:
        if not is_authenticated_private_chat(message):
            await message.answer("مراجعة طلبات التحقق متاحة في محادثتك الخاصة مع البوت فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        if admin_user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        response = await handler.list_pending(admin_user_id)
        if not response.ok:
            await message.answer(response.message or "تعذر تحميل طلبات التحقق.")
            return
        if not response.submissions:
            await message.answer("لا توجد طلبات تحقق معلقة.")
            return
        await message.answer("طلبات التحقق المعلقة:")
        for submission in response.submissions[:IDENTITY_REVIEW_PAGE_LIMIT]:
            try:
                await message.answer_photo(
                    submission.qr_image_file_id,
                    caption=_identity_review_caption(submission),
                    reply_markup=_identity_review_markup(submission.submission_id),
                )
            except Exception:
                await message.answer("تعذر عرض صورة QR لأحد الطلبات. حاول لاحقًا.")
        if len(response.submissions) > IDENTITY_REVIEW_PAGE_LIMIT:
            await message.answer("توجد طلبات إضافية. راجع هذه الدفعة أولاً ثم أعد الأمر.")

    @router.callback_query(F.data.regexp(IDENTITY_REVIEW_CALLBACK))
    async def review_identity_submission(query: CallbackQuery, state: FSMContext) -> None:
        parsed = parse_identity_review_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        if not is_authenticated_private_chat(query):
            await query.answer("المراجعة متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        admin_user_id = authenticated_telegram_user_id(query)
        if admin_user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        action, submission_id = parsed
        if action == "reject":
            await state.clear()
            await state.update_data(identity_submission_id=str(submission_id))
            await state.set_state(IdentityReviewState.rejection_reason)
            await query.answer()
            if query.message is not None:
                await query.message.answer("أرسل سبب الرفض (من 1 إلى 500 حرف).")
            return
        response = await handler.approve(admin_user_id, submission_id)
        await query.answer(response.message or "تعذر تحديث طلب التحقق.", show_alert=not response.ok)
        if response.ok and query.message is not None:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                LOGGER.warning("Could not remove completed identity review controls.")

    @router.message(IdentityReviewState.rejection_reason, F.text)
    async def receive_identity_rejection_reason(message: Message, state: FSMContext) -> None:
        if not is_authenticated_private_chat(message):
            await state.clear()
            await message.answer("إرسال سبب الرفض متاح في محادثتك الخاصة مع البوت فقط.")
            return
        admin_user_id = authenticated_telegram_user_id(message)
        values = await state.get_data()
        try:
            submission_id = UUID(str(values.get("identity_submission_id", "")))
        except ValueError:
            await state.clear()
            await message.answer("انتهت جلسة المراجعة. افتح قائمة الطلبات من جديد.")
            return
        reason = (message.text or "").strip()
        if not 1 <= len(reason) <= 500:
            await message.answer("أرسل سبب رفض بين 1 و500 حرف.")
            return
        if admin_user_id is None:
            await state.clear()
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        response = await handler.reject(admin_user_id, submission_id, reason)
        if response.ok:
            await state.clear()
        await message.answer(response.message or "تعذر تحديث طلب التحقق.")

    @router.message(IdentityReviewState.rejection_reason)
    async def require_identity_rejection_reason(message: Message) -> None:
        await message.answer("أرسل سبب الرفض كنص بين 1 و500 حرف.")

    return router

def is_authenticated_private_chat(message_or_callback: Message | CallbackQuery) -> bool:
    """Sensitive review data may only be rendered in the sender's private chat."""

    user_id = authenticated_telegram_user_id(message_or_callback)
    message = (
        message_or_callback.message
        if isinstance(message_or_callback, CallbackQuery)
        else message_or_callback
    )
    chat = getattr(message, "chat", None)
    return (
        user_id is not None
        and getattr(chat, "type", None) == "private"
        and getattr(chat, "id", None) == user_id
    )
