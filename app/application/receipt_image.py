from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_RECEIPT_BYTES = 5 * 1024 * 1024
MAX_RECEIPT_PIXELS = 20_000_000
MAX_RECEIPT_WIDTH = 6000
MAX_RECEIPT_HEIGHT = 6000


@dataclass(frozen=True, slots=True)
class InspectedReceiptImage:
    mime_type: str
    width: int
    height: int
    size_bytes: int
    content: bytes


class ReceiptImageValidationError(ValueError):
    pass


class ReceiptImageInspectorImpl:
    async def inspect_bytes(self, content: bytes, declared_mime_type: str) -> InspectedReceiptImage:
        if not isinstance(content, bytes):
            raise ReceiptImageValidationError("receipt image content must be bytes")
        if not content:
            raise ReceiptImageValidationError("receipt image is empty")
        if len(content) > MAX_RECEIPT_BYTES:
            raise ReceiptImageValidationError("receipt image exceeds the 5 MB size limit")

        expected_formats = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
            "image/webp": "WEBP",
        }
        if not isinstance(declared_mime_type, str):
            raise ReceiptImageValidationError("unsupported receipt image type")
        normalized_mime = declared_mime_type.strip().lower()
        expected_format = expected_formats.get(normalized_mime)
        if expected_format is None:
            raise ReceiptImageValidationError("unsupported receipt image type")

        try:
            with Image.open(BytesIO(content)) as image:
                actual_format = image.format
                if actual_format != expected_format:
                    raise ReceiptImageValidationError("declared image type does not match file content")
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise ReceiptImageValidationError("receipt image dimensions are invalid")
                if width > MAX_RECEIPT_WIDTH or height > MAX_RECEIPT_HEIGHT:
                    raise ReceiptImageValidationError("receipt image dimensions exceed the allowed limit")
                if width * height > MAX_RECEIPT_PIXELS:
                    raise ReceiptImageValidationError("receipt image contains too many pixels")
                image.verify()
        except ReceiptImageValidationError:
            raise
        except Image.DecompressionBombError as exc:
            raise ReceiptImageValidationError("receipt image exceeds safe decoding limits") from exc
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ReceiptImageValidationError("image could not be safely decoded") from exc

        return InspectedReceiptImage(
            mime_type=normalized_mime,
            width=width,
            height=height,
            size_bytes=len(content),
            content=content,
        )
