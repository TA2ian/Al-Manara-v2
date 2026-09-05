from __future__ import annotations

from dataclasses import dataclass

from app.application.admin_payment_account import AdminPaymentAccount, AdminPaymentAccountService
from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


PAYMENT_ACCOUNT_ERROR_MESSAGE = "Payment account changes could not be completed. Please retry."


@dataclass(frozen=True, slots=True)
class TelegramAdminPaymentAccountResponse:
    ok: bool
    account: AdminPaymentAccount | None = None
    accounts: tuple[AdminPaymentAccount, ...] = ()
    message: str = ""


class TelegramAdminPaymentAccountHandler:
    def __init__(self, service: AdminPaymentAccountService) -> None:
        self._service = service

    async def list(self, admin_user_id: int, actor_type: str) -> TelegramAdminPaymentAccountResponse:
        try:
            accounts = await self._service.list(admin_user_id, actor_type)
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(False, message="Payment accounts could not be loaded. Please retry.")
        return TelegramAdminPaymentAccountResponse(True, accounts=tuple(accounts), message="Payment accounts loaded.")

    async def upsert(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            account = await self._service.upsert(admin_user_id, actor_type, currency, setup)
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(False, message="Payment account could not be saved. Please retry.")
        return TelegramAdminPaymentAccountResponse(True, account=account, message="Payment account saved.")

    async def set_active(
        self,
        admin_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
    ) -> TelegramAdminPaymentAccountResponse:
        try:
            account = await self._service.set_active(admin_user_id, actor_type, currency, is_active)
        except (ValueError, PermissionError):
            return TelegramAdminPaymentAccountResponse(
                False, message=PAYMENT_ACCOUNT_ERROR_MESSAGE
            )
        except Exception:
            return TelegramAdminPaymentAccountResponse(False, message="Payment account status could not be changed. Please retry.")
        return TelegramAdminPaymentAccountResponse(True, account=account, message="Payment account status updated.")
