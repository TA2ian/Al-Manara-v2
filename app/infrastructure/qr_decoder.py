from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 10_000


class QRDecodeError(ValueError):
    """Raised when an uploaded image cannot be safely decoded as a QR payload."""


def decode_qr_payload(content: bytes) -> str:
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise QRDecodeError("QR image exceeds size limit")
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise QRDecodeError("QR image dimensions are invalid")
            if width * height > MAX_IMAGE_PIXELS:
                raise QRDecodeError("QR image has too many pixels")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise QRDecodeError("QR image is not a valid image") from exc

    try:
        with Image.open(BytesIO(content)) as image:
            rgb = image.convert("RGB")
            frame = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise QRDecodeError("QR image could not be decoded") from exc

    detector = cv2.QRCodeDetector()
    payload, _, _ = detector.detectAndDecode(frame)
    payload = (payload or "").strip()
    if not payload:
        raise QRDecodeError("QR code was not detected")
    if len(payload) > 2048:
        raise QRDecodeError("QR payload is too large")
    return payload
