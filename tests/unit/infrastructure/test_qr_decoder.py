import cv2
import numpy as np
import pytest

from app.infrastructure.qr_decoder import QRDecodeError, decode_qr_payload


def test_decode_qr_payload_reads_real_qr_bytes() -> None:
    encoder = cv2.QRCodeEncoder_create()
    image = encoder.encode("ethereum:0x1234567890123456789012345678901234567890")
    bordered = cv2.copyMakeBorder(image, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    enlarged = cv2.resize(bordered, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".png", enlarged)
    assert ok
    assert decode_qr_payload(encoded.tobytes()) == "ethereum:0x1234567890123456789012345678901234567890"


def test_decode_qr_payload_rejects_non_image() -> None:
    with pytest.raises(QRDecodeError, match="valid image"):
        decode_qr_payload(b"not-an-image")


def test_decode_qr_payload_rejects_missing_qr() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    with pytest.raises(QRDecodeError, match="QR code was not detected"):
        decode_qr_payload(encoded.tobytes())


def test_decode_qr_payload_rejects_oversized_payload() -> None:
    with pytest.raises(QRDecodeError, match="size limit"):
        decode_qr_payload(b"x" * (5 * 1024 * 1024 + 1))
