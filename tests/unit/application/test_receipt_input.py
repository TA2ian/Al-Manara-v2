from app.application.receipt_input import ReceiptInputDecision, classify_receipt_input


def test_pdf_mime_is_guidance_only() -> None:
    result = classify_receipt_input(mime_type="application/pdf", filename="receipt.pdf")
    assert result.decision is ReceiptInputDecision.GUIDE_USER
    assert result.user_message_key == "receipt.pdf_guidance"


def test_pdf_filename_is_guidance_only_even_without_mime() -> None:
    result = classify_receipt_input(mime_type=None, filename="receipt.pdf")
    assert result.decision is ReceiptInputDecision.GUIDE_USER


def test_supported_images_enter_processing() -> None:
    for mime_type in ("image/jpeg", "image/png", "image/webp"):
        result = classify_receipt_input(mime_type=mime_type, filename="receipt")
        assert result.decision is ReceiptInputDecision.PROCESS_IMAGE


def test_unknown_file_is_guidance_only() -> None:
    result = classify_receipt_input(mime_type="application/octet-stream", filename="receipt")
    assert result.decision is ReceiptInputDecision.GUIDE_USER
    assert result.user_message_key == "receipt.unsupported_format"
