from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.customer_identity import CustomerIdentityService, CustomerIdentitySubmission

IDENTITY_REVIEW_RETRY_MESSAGE = "تعذر تحديث طلب التحقق حاليًا. حاول مجددًا."


@dataclass(frozen=True, slots=True)
class TelegramIdentityReviewResponse:
    ok: bool
    submissions: tuple[CustomerIdentitySubmission, ...] = ()
    message: str = ""


class CustomerIdentityReviewApplication(Protocol):
    async def list_pending(
        self, admin_telegram_user_id: int, actor_type: str
    ) -> tuple[CustomerIdentitySubmission, ...]: ...

    async def approve(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID
    ) -> None: ...

    async def reject(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID, reason: str
    ) -> None: ...


class TelegramAdminCustomerIdentityHandler:
    """Safe Telegram-facing boundary for primary-admin identity review."""

    def __init__(self, service: CustomerIdentityReviewApplication | CustomerIdentityService) -> None:
        self._service = service

    async def list_pending(self, admin_user_id: int) -> TelegramIdentityReviewResponse:
        try:
            submissions = await self._service.list_pending(admin_user_id, "primary")
        except PermissionError:
            return TelegramIdentityReviewResponse(False, message="غير مصرح لك بمراجعة طلبات التحقق.")
        except (ValueError, RuntimeError):
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        except Exception:
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        return TelegramIdentityReviewResponse(True, submissions=submissions, message="تم تحميل طلبات التحقق.")

    async def approve(self, admin_user_id: int, submission_id: UUID) -> TelegramIdentityReviewResponse:
        if not isinstance(submission_id, UUID):
            return TelegramIdentityReviewResponse(False, message="طلب التحقق غير صالح.")
        try:
            await self._service.approve(admin_user_id, "primary", submission_id)
        except PermissionError:
            return TelegramIdentityReviewResponse(False, message="غير مصرح لك بمراجعة طلبات التحقق.")
        except (ValueError, RuntimeError):
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        except Exception:
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        return TelegramIdentityReviewResponse(True, message="تم اعتماد بيانات العميل.")

    async def reject(
        self, admin_user_id: int, submission_id: UUID, reason: str
    ) -> TelegramIdentityReviewResponse:
        if not isinstance(submission_id, UUID) or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            return TelegramIdentityReviewResponse(False, message="سبب الرفض غير صالح.")
        try:
            await self._service.reject(admin_user_id, "primary", submission_id, reason)
        except PermissionError:
            return TelegramIdentityReviewResponse(False, message="غير مصرح لك بمراجعة طلبات التحقق.")
        except (ValueError, RuntimeError):
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        except Exception:
            return TelegramIdentityReviewResponse(False, message=IDENTITY_REVIEW_RETRY_MESSAGE)
        return TelegramIdentityReviewResponse(True, message="تم رفض طلب التحقق.")