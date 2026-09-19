from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.disable_wallet import DisableWalletCommand, DisableWalletResult
from app.application.list_wallets import ListWalletsCommand
from app.application.register_wallet import RegisterWalletCommand, RegisterWalletResult
from app.runtime.telegram.messages import customer_safe_message


@dataclass(frozen=True, slots=True)
class TelegramWalletInput:
    user_id: int
    wallet_id: UUID | None = None
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class TelegramWalletRegistrationInput:
    user_id: int
    address: str
    network: str
    qr_address: str
    qr_image_file_id: str
    label: str


@dataclass(frozen=True, slots=True)
class TelegramWalletResponse:
    ok: bool
    text: str


@dataclass(frozen=True, slots=True)
class TelegramWalletChoicesResponse:
    """Verified wallets suitable for a customer order, with no presentation policy."""

    ok: bool
    wallets: tuple[object, ...] = ()
    text: str = ""


class WalletMessages:
    INVALID = "بيانات المحفظة غير صالحة."
    NOT_FOUND = "المحفظة غير متاحة لهذا الحساب."
    EMPTY = "لا توجد محافظ موثقة متاحة للاستخدام."
    LIST_HEADER = "المحافظ الموثقة المتاحة:"
    PENDING = "تم تسجيل المحفظة وبانتظار التحقق."
    DISABLED = "تم تعطيل المحفظة ولن يمكن استخدامها لطلبات جديدة."
    ALREADY_DISABLED = "المحفظة معطلة بالفعل."
    CONFIRMATION_REQUIRED = "يرجى تأكيد تعطيل المحفظة لإتمام العملية."
    ERROR = "تعذر تنفيذ عملية المحفظة حاليًا."


class WalletListingService(Protocol):
    async def execute(self, command: ListWalletsCommand): ...


class WalletRegistrationService(Protocol):
    async def execute(self, command: RegisterWalletCommand) -> RegisterWalletResult: ...


class WalletDisableService(Protocol):
    async def execute(self, command: DisableWalletCommand) -> DisableWalletResult: ...


@dataclass(frozen=True, slots=True)
class TelegramWalletHandler:
    """Framework-neutral Telegram adapter for customer wallet management."""

    listing: WalletListingService
    registration: WalletRegistrationService
    disabling: WalletDisableService

    async def list(self, user_id: int) -> TelegramWalletResponse:
        try:
            wallets = await self.listing.execute(ListWalletsCommand(user_id=user_id))
        except (ValueError, LookupError):
            return TelegramWalletResponse(False, WalletMessages.INVALID)
        except Exception:
            return TelegramWalletResponse(False, WalletMessages.ERROR)

        if not wallets:
            return TelegramWalletResponse(True, WalletMessages.EMPTY)
        lines = [WalletMessages.LIST_HEADER]
        for wallet in wallets:
            lines.append(f"• {wallet.network.value}: {wallet.address} ({wallet.wallet_id})")
        return TelegramWalletResponse(True, "\n".join(lines))

    async def list_available_for_order(self, user_id: int) -> TelegramWalletChoicesResponse:
        """Return application-selected wallets for a Telegram order flow.

        The router deliberately receives wallet objects only through this adapter;
        it never reads a persistence repository itself.
        """
        if user_id <= 0:
            return TelegramWalletChoicesResponse(False, text=WalletMessages.INVALID)
        try:
            wallets = tuple(await self.listing.execute(ListWalletsCommand(user_id=user_id)))
        except (ValueError, LookupError):
            return TelegramWalletChoicesResponse(False, text=WalletMessages.INVALID)
        except Exception:
            return TelegramWalletChoicesResponse(False, text=WalletMessages.ERROR)
        return TelegramWalletChoicesResponse(True, wallets=wallets)

    async def register(self, data: TelegramWalletRegistrationInput) -> TelegramWalletResponse:
        if data.user_id <= 0:
            return TelegramWalletResponse(False, WalletMessages.INVALID)
        try:
            result = await self.registration.execute(
                RegisterWalletCommand(
                    user_id=data.user_id,
                    address=data.address,
                    network=data.network,
                    qr_address=data.qr_address,
                    qr_image_file_id=data.qr_image_file_id,
                    label=data.label,
                )
            )
        except ValueError:
            return TelegramWalletResponse(False, WalletMessages.INVALID)
        except Exception:
            return TelegramWalletResponse(False, WalletMessages.ERROR)
        if result.status != "pending":
            return TelegramWalletResponse(False, WalletMessages.ERROR)
        return TelegramWalletResponse(True, WalletMessages.PENDING)

    async def disable(self, data: TelegramWalletInput) -> TelegramWalletResponse:
        if data.user_id <= 0 or data.wallet_id is None:
            return TelegramWalletResponse(False, WalletMessages.INVALID)
        try:
            result = await self.disabling.execute(
                DisableWalletCommand(wallet_id=data.wallet_id, user_id=data.user_id, confirmed=data.confirmed)
            )
        except LookupError:
            return TelegramWalletResponse(False, WalletMessages.NOT_FOUND)
        except ValueError:
            return TelegramWalletResponse(False, WalletMessages.INVALID)
        except Exception:
            return TelegramWalletResponse(False, WalletMessages.ERROR)
        if result.confirmation_required:
            return TelegramWalletResponse(
                False,
                customer_safe_message(result.message, WalletMessages.CONFIRMATION_REQUIRED),
            )
        if result.disabled:
            return TelegramWalletResponse(True, WalletMessages.DISABLED)
        if "already disabled" in result.message:
            return TelegramWalletResponse(True, WalletMessages.ALREADY_DISABLED)
        return TelegramWalletResponse(False, WalletMessages.ERROR)
