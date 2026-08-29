from __future__ import annotations

import re

_OPERATION_NUMBER_RE = re.compile(r"[^A-Z0-9]")


def normalize_operation_number(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = _OPERATION_NUMBER_RE.sub("", raw.strip().upper())
    return normalized or None


def operation_numbers_match(expected: str | None, extracted: str | None) -> bool | None:
    normalized_expected = normalize_operation_number(expected)
    normalized_extracted = normalize_operation_number(extracted)
    if normalized_expected is None or normalized_extracted is None:
        return None
    return normalized_expected == normalized_extracted
