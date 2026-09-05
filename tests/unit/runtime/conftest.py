from __future__ import annotations

from app.runtime.telegram.admin_identity_review import parse_identity_review_callback


def pytest_collection_modifyitems(items):
    """Bridge the extracted parser into the pre-extraction runtime test module."""
    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        module_file = getattr(module, "__file__", "") or ""
        if module_file.endswith("test_telegram_bot_runtime.py"):
            setattr(module, "parse_identity_review_callback", parse_identity_review_callback)
