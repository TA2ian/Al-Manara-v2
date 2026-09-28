from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
import logging
from typing import Awaitable, Callable

from app.application.receipt_image import ReceiptImageInspectorImpl
from app.application.receipt_image_normalizer import ReceiptImageNormalizer
from app.application.receipt_ocr_normalizer import normalize_amount, normalize_currency_field, normalize_transaction_datetime
from app.application.receipt_verification_service import ReceiptFinancialVerificationService, ReceiptVerificationInput
from app.domain.receipt_attempt import ReceiptAttemptStatus
from app.domain.receipt_ocr import OcrField, OcrPort
from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision


logger = logging.getLogger(__name__)\nProgressCallback = Callable[[int, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ReceiptSubmission:
    order_id: UUID
    attempt_id: UUID
    telegram_file_id: str
    mime_type: str


class ReceiptAttemptFinalizer:
    async def finalize(self, attempt_id: UUID, status: ReceiptAttemptStatus, reason: str | None = None):
        raise NotImplementedError


class ReceiptSubmissionOrchestrator:
    def __init__(self, inspector: ReceiptImageInspectorImpl, normalizer: ReceiptImageNormalizer, ocr: OcrPort, verification: ReceiptFinancialVerificationService, finalizer: ReceiptAttemptFinalizer) -> None:
        self._inspector = inspector
        self._normalizer = normalizer
        self._ocr = ocr
        self._verification = verification
        self._finalizer = finalizer

    async def process(self, submission: ReceiptSubmission, image_bytes: bytes, progress: ProgressCallback | None = None):
        finalized = False
        try:
            if progress is not None:\n                await progress(0, "بدء فحص الإيصال")\n            inspected = await self._inspector.inspect_bytes(image_bytes, submission.mime_type)
            if progress is not None:\n                await progress(20, "تم التحقق من سلامة الصورة")\n            normalized = self._normalizer.normalize(inspected.content, inspected.mime_type)\n            if progress is not None:\n                await progress(40, "تم تجهيز الصورة للتحقق")\n            ocr_result = await self._ocr.extract(normalized.content, normalized.mime_type, submission.attempt_id)
            fields = ocr_result.fields\n            if progress is not None:\n                await progress(65, "تم استخراج بيانات الإيصال")\n
            raw_amount = fields[OcrField.AMOUNT].value if OcrField.AMOUNT in fields else None
            raw_currency = fields[OcrField.CURRENCY].value if OcrField.CURRENCY in fields else None
            amount = normalize_amount(raw_amount) if raw_amount else None
            currency = normalize_currency_field(raw_currency)
            extracted = ExtractedReceiptData(
                receipt_id=submission.attempt_id,
                amount=amount,
                currency=currency.value if currency is not None else None,
                reference=fields[OcrField.REFERENCE].value if OcrField.REFERENCE in fields else None,
                network=fields[OcrField.NETWORK].value if OcrField.NETWORK in fields else None,
                confidence=min((field.confidence for field in fields.values()), default=0),
                transaction_datetime=(normalize_transaction_datetime(fields[OcrField.TRANSACTION_DATETIME].value) if OcrField.TRANSACTION_DATETIME in fields else None),
            )
            verification = await self._verification.verify(ReceiptVerificationInput(submission.order_id, extracted))
            decision = verification.evidence.decision\n            if progress is not None:\n                await progress(90, "تمت مقارنة المبلغ والعملة والوقت ورقم الطلب")\n\n            if decision is VerificationDecision.VERIFIED:
                finalized = True
                result = await self._finalizer.finalize(submission.attempt_id, ReceiptAttemptStatus.VERIFIED)\n                if progress is not None:\n                    await progress(100, "اكتمل التحقق")\n                return result

            reason = ";".join(verification.evidence.reasons) or decision.value
            status = ReceiptAttemptStatus.ESCALATED if decision is VerificationDecision.SUSPICIOUS and submission.attempt_id is not None and await self._is_third_attempt(submission.attempt_id) else ReceiptAttemptStatus.FAILED
            finalized = True
            result = await self._finalizer.finalize(submission.attempt_id, status, reason)\n            if progress is not None:\n                await progress(100, "اكتمل التحقق")\n            return result
        except Exception:
            if not finalized:
                logger.exception("receipt processing failed", extra={"receipt_attempt_id": str(submission.attempt_id)})
                await self._finalizer.finalize(
                    submission.attempt_id,
                    ReceiptAttemptStatus.FAILED,
                    "receipt processing failed",
                )
            raise

    async def _is_third_attempt(self, attempt_id: UUID) -> bool:
        checker = getattr(self._finalizer, "is_third_attempt", None)
        if checker is None:
            return False
        return bool(await checker(attempt_id))
