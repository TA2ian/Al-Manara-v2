from decimal import Decimal
from app.infrastructure.receipt_ocr_tesseract import TesseractReceiptOcr
from app.domain.receipt_ocr import OcrField


def test_tesseract_parser_extracts_amount_currency_and_transaction_time():
    fields = TesseractReceiptOcr._extract_fields(
        "المبلغ: 100.01 USD التاريخ 28/09/2026 الوقت 12:30",
        Decimal("0.91"),
    )
    assert fields[OcrField.AMOUNT].value == "100.01"
    assert fields[OcrField.CURRENCY].value == "USD"
    assert fields[OcrField.TRANSACTION_DATETIME].value == "28/09/2026 12:30"


def test_tesseract_parser_does_not_guess_amount_from_unlabelled_numbers():
    fields = TesseractReceiptOcr._extract_fields(
        "28/09/2026 12:30 100.01 USD",
        Decimal("0.91"),
    )
    assert OcrField.AMOUNT not in fields


def test_tesseract_tsv_confidence_is_bounded():
    raw = b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t90.0\tUSD\n"
    text, confidence = TesseractReceiptOcr._parse_tsv(raw)
    assert text == "USD"
    assert confidence == Decimal("0.900")
