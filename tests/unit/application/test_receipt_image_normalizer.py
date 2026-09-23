from io import BytesIO

import pytest
from PIL import Image

from app.application.receipt_image_normalizer import ReceiptImageNormalizer
from app.application.receipt_image_policy import ReceiptImagePolicy


def make_image(width: int, height: int, image_format: str) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_large_valid_image_is_resized_to_working_resolution() -> None:
    policy = ReceiptImagePolicy(max_longest_side_px=6000, max_pixels=20_000_000, working_longest_side_px=3000)
    normalizer = ReceiptImageNormalizer(policy)
    result = normalizer.normalize(make_image(4000, 3000, "JPEG"), "image/jpeg")
    assert max(result.width, result.height) == 3000
    assert result.mime_type == "image/jpeg"


def test_png_remains_png() -> None:
    normalizer = ReceiptImageNormalizer()
    result = normalizer.normalize(make_image(1200, 900, "PNG"), "image/png")
    assert result.mime_type == "image/png"
    assert result.content.startswith(b"\x89PNG")


def test_image_below_minimum_shortest_side_is_rejected() -> None:
    normalizer = ReceiptImageNormalizer()
    with pytest.raises(ValueError, match="normalization failed"):
        normalizer.normalize(make_image(1000, 400, "JPEG"), "image/jpeg")
