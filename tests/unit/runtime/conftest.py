from __future__ import annotations

import pytest

from app.runtime.telegram.admin_identity_review import parse_identity_review_callback


def pytest_collection_modifyitems(items):
    """Bridge extracted APIs and annotate legacy expectations superseded by navigation policy."""
    legacy_runtime_module = "test_telegram_bot_runtime.py"
    superseded_tests = {
        "test_router_dispatches_addressed_group_orders_without_command_help": "Customer order history is now private-chat only.",
        "test_router_dispatches_start_and_orders_through_aiogram": "Customer /start now opens the dashboard instead of command help.",
    }
    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        module_file = getattr(module, "__file__", "") or ""
        if module_file.endswith(legacy_runtime_module):
            setattr(module, "parse_identity_review_callback", parse_identity_review_callback)
        reason = superseded_tests.get(item.name)
        if reason:
            item.add_marker(pytest.mark.xfail(strict=True, reason=reason))
