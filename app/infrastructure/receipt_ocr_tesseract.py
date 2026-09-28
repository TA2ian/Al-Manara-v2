from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Sequence
from uuid import UUID

from app.domain.receipt_ocr import OcrField, OcrFieldValue, OcrResult


class TesseractReceiptOcr:
    """Local, fixed-command OCR adapter for customer receipt images only."""

    _SUPPORTED = frozenset({"image/jpeg", "image/png", "image/webp"})
    _LANGUAGES = "ara+eng"
    _PSM = "6"
    _TIMEOUT_SECONDS = 12.0
    _MAX_BYTES = 5 * 1024 * 1024
    _EXECUTABLE = "tesseract"

    async def extract(self, image: bytes, mime_type: str, receipt_id: UUID) -> OcrResult:
        mime = mime_type.strip().lower()
        if mime not in self._SUPPORTED:
            raise ValueError("unsupported OCR image type")
        if not isinstance(image, bytes) or not image or len(image) > self._MAX_BYTES:
            raise ValueError("OCR image size is invalid")

        with tempfile.TemporaryDirectory(prefix="almanara-ocr-") as directory:
            input_path = Path(directory) / "receipt"
            input_path.write_bytes(image)
            os.chmod(input_path, 0o600)
            command: Sequence[str] = (
                self._EXECUTABLE,
                str(input_path),
                "stdout",
                "--tsv",
                "-l",
                self._LANGUAGES,
                "--psm",
                self._PSM,
            )
            try:
                completed = await asyncio.to_thread(
                    subprocess.run,
                    list(command),
                    shell=False,
                    check=False,
                    capture_output=True,
                    timeout=self._TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("OCR timed out") from exc
            except OSError as exc:
                raise RuntimeError("local OCR engine is unavailable") from exc

        if completed.returncode != 0:
            raise RuntimeError("OCR engine failed")
        text, confidence = self._parse_tsv(completed.stdout)
        fields = self._extract_fields(text, confidence)
        version = await self._version()
        return OcrResult(
            receipt_id=receipt_id,
            fields=fields,
            provider="tesseract",
            provider_version=version,
        )

    async def _version(self) -> str:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [self._EXECUTABLE, "--version"],
                shell=False,
                check=False,
                capture_output=True,
                timeout=3.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("unable to determine OCR engine version") from exc
        if completed.returncode != 0:
            raise RuntimeError("unable to determine OCR engine version")
        first_line = completed.stdout.decode("utf-8", errors="replace").splitlines()
        if not first_line or not first_line[0].strip():
            raise RuntimeError("OCR engine version is unavailable")
        return first_line[0].strip()[:120]

    @classmethod
    def _extract_fields(cls, text: str, confidence: Decimal) -> dict[OcrField, OcrFieldValue]:
        normalized = cls._normalize_digits(text)
        fields: dict[OcrField, OcrFieldValue] = {}

        amount_match = re.search(
            r"(?:المبلغ|amount|total|الإجمالي|القيمة)\s*[:：]?\s*([$€£]?\s*[0-9][0-9,\.\s]*)",
            normalized,
            re.IGNORECASE,
        )
        if amount_match is not None:
            raw = amount_match.group(1) if amount_match.lastindex else amount_match.group(0)
            amount = re.sub(r"[^0-9,.-]", "", raw).replace(",", "")
            try:
                parsed = Decimal(amount)
            except Exception:
                parsed = None
            if parsed is not None and parsed.is_finite() and parsed > 0:
                fields[OcrField.AMOUNT] = OcrFieldValue(format(parsed, "f"), confidence)

        currency_match = re.search(
            r"(USD|US\s*DOLLAR|\$|دولار|SYP|ل\.س|ليرة(?:\s+سورية)?|سورية)",
            normalized,
            re.IGNORECASE,
        )
        if currency_match is not None:
            value = currency_match.group(1)
            fields[OcrField.CURRENCY] = OcrFieldValue(value, confidence)

        order_match = re.search(r"\b(ORD-[A-Z0-9]{12})\b", normalized, re.IGNORECASE)
        if order_match is not None:
            fields[OcrField.REFERENCE] = OcrFieldValue(order_match.group(1).upper(), confidence)

        date_match = re.search(r"\b([0-3]?[0-9][/-][0-1]?[0-9][/-](?:20)?[0-9]{2})\b", normalized)
        time_match = re.search(r"\b([0-2]?[0-9]:[0-5][0-9](?::[0-5][0-9])?)\b", normalized)
        if date_match is not None and time_match is not None:
            fields[OcrField.TRANSACTION_DATETIME] = OcrFieldValue(
                f"{date_match.group(1)} {time_match.group(1)}",
                confidence,
            )

        return fields

    @staticmethod
    def _parse_tsv(raw: bytes) -> tuple[str, Decimal]:
        rows = csv.reader(io.StringIO(raw.decode("utf-8", errors="replace")), delimiter="\t")
        words: list[str] = []
        confidences: list[Decimal] = []
        try:
            header = next(rows)
        except StopIteration:
            return "", Decimal("0")
        if "text" not in header or "conf" not in header:
            return "", Decimal("0")
        text_index = header.index("text")
        conf_index = header.index("conf")
        for row in rows:
            if len(row) <= max(text_index, conf_index):
                continue
            value = row[text_index].strip()
            if value:
                words.append(value)
            try:
                conf = Decimal(row[conf_index])
            except Exception:
                continue
            if Decimal("0") <= conf <= Decimal("100"):
                confidences.append(conf / Decimal("100"))
        confidence = (sum(confidences, Decimal("0")) / Decimal(len(confidences))) if confidences else Decimal("0")
        return " ".join(words), confidence.quantize(Decimal("0.001"))

    @staticmethod
    def _normalize_digits(value: str) -> str:
        return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
