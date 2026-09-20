from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.admin_payment_account import AdminPaymentAccount, AdminPaymentAccountService
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


PAYMENT_ACCOUNT_ERROR_MESSAGE = "Payment account changes could not be completed. Please retry."
PAYMENT_ACCOUNT_CONFIRMATION_MESSAGE = "Payment account change is ready for confirmation."


@dataclass(frozen=True, slots=True)
class TelegramAdminPaymentAccountResponse:
    ok: bool
    account: AdminPaymentAccount | None = None
    accounts: tuple[AdminPaymentAccount, ...] = ()
    confirmation_id: UUID | None = None
    message: str = ""


class TelegramAdminPaymentAccountHandler:
    """Framework-neutral adapter for the secure ShamCash management flow.

    Mutations are deliberately split into request/confirm steps so a Telegram
    inline confirmation button can only complete a short-lived, server-bound
    confirmation. The persistence layer re-validates the session and consumes
    the confirmation atomically.
    """

    def __init__(self, service: AdminPaymentAccountService) -> None:
        self._service = service

    async def list(
        self,
        admin_user_id: int,
        actor_type: str,
        session_id: UUID,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            accounts = await self._service.list(admin_user_id, actor_type, session_id)
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(
                False, message="Payment accounts could not be loaded. Please retry."
            )
        return TelegramAdminPaymentAccountResponse(
            True,
            accounts=tuple(accounts),
            message="Payment accounts loaded.",
        )

    async def request_upsert_confirmation(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
        session_id: UUID,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            confirmation_id = await self._service.request_upsert_confirmation(
                admin_user_id,
                actor_type,
                currency,
                setup,
                session_id,
            )
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(
                False, message="Payment account confirmation could not be prepared. Please retry."
            )
        return TelegramAdminPaymentAccountResponse(
            True,
            confirmation_id=confirmation_id,
            message=PAYMENT_ACCOUNT_CONFIRMATION_MESSAGE,
        )

    async def confirm_upsert(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
        session_id: UUID,
        confirmation_id: UUID,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            account = await self._service.upsert(
                admin_user_id,
                actor_type,
                currency,
                setup,
                session_id,
                confirmation_id,
            )
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(
                False, message="Payment account could not be saved. Please retry."
            )
        return TelegramAdminPaymentAccountResponse(
            True,
            account=account,
            message="Payment account saved.",
        )

    async def request_set_active_confirmation(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
        session_id: UUID,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            confirmation_id = await self._service.request_set_active_confirmation(
                admin_user_id,
                actor_type,
                currency,
                is_active,
                session_id,
            )
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(
                False, message="Payment account confirmation could not be prepared. Please retry."
            )
        return TelegramAdminPaymentAccountResponse(
            True,
            confirmation_id=confirmation_id,
            message=PAYMENT_ACCOUNT_CONFIRMATION_MESSAGE,
        )

    async def confirm_set_active(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
        session_id: UUID,
        confirmation_id: UUID,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            account = await self._service.set_active(
                admin_user_id,
                actor_type,
                currency,
                is_active,
                session_id,
                confirmation_id,
            )
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(
                False, message="Payment account status could not be changed. Please retry."
            )
        return TelegramAdminPaymentAccountResponse(
            True,
            account=account,
            message="Payment account status updated.",
        )
