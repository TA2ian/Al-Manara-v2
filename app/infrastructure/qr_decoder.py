from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 10_000
MAX_QR_PAYLOAD_LENGTH = 2048
_QR_BORDER = 32


class QRDecodeError(ValueError):
    """Raised when an uploaded image cannot be safely decoded as a QR payload."""


def _decode_with_detector(detector: cv2.QRCodeDetector, frame: np.ndarray) -> str:
    payload, _, _ = detector.detectAndDecode(frame)
    return (payload or "").strip()


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
            variants = (
                rgb,
                ImageOps.expand(rgb, border=_QR_BORDER, fill="white"),
            )
            detector = cv2.QRCodeDetector()
            for variant in variants:
                frame = cv2.cvtColor(np.asarray(variant), cv2.COLOR_RGB2BGR)
                candidates = (frame,)
                height, width = frame.shape[:2]
                if max(height, width) < 4000 and height * 4 <= MAX_IMAGE_PIXELS and width * 4 <= MAX_IMAGE_PIXELS:
                    candidates = (
                        frame,
                        cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST),
                    )
                for candidate in candidates:
                    payload = _decode_with_detector(detector, candidate)
                    if payload:
                        if len(payload) > MAX_QR_PAYLOAD_LENGTH:
                            raise QRDecodeError("QR payload is too large")
                        return payload
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise QRDecodeError("QR image could not be decoded") from exc

    raise QRDecodeError("QR code was not detected")
