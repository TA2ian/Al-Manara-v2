from __future__ import annotations

from app.runtime.telegram.admin_identity_review import parse_identity_review_callback


def pytest_collection_modifyitems(items):
    """Provide the extracted callback parser to the legacy runtime test module.

    The runtime tests predate the router extraction and reference this helper as
    a module-level symbol. Keep that compatibility local to the affected test
    module until its import list can be edited without replacing the full file.
    """
    for item in items:
        module = getattr(item, "module", None)
        if module is not None and module.__name__ == "tests.unit.runtime.test_telegram_bot_runtime":
            setattr(module, "parse_identity_review_callback", parse_identity_review_callback)
