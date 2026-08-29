# Open Decisions Before Implementation

This document is the implementation gate. No production implementation may silently choose a value listed here.

## Business decisions

### All business decisions currently required for implementation

**Status: CLOSED.**

The financial and administrator policy decisions are accepted and recorded in their authoritative ADRs.

See:

- `ADR-005-rounding-and-tolerance.md` — financial precision, rounding, receipt tolerance, and tolerance timing.
- `ADR-006-mvp-scope-reconciliation.md` — MVP receipt scope and TOTP step-up policy.

## Engineering decisions

**Status: CLOSED for the initial implementation baseline.**

The following decisions are accepted and recorded:

- Python 3.13.x — `ADR-007-python-runtime.md`.
- aiogram 3.31.0, confined to Telegram presentation — `ADR-008-aiogram-runtime.md`.
- PostgreSQL 17 with SQLAlchemy 2.x and Alembic — `ADR-009-postgresql-and-persistence.md`.
- Redis for shared ephemeral state, rate limiting, idempotency, and coordination — `ADR-012-redis-shared-ephemeral-state.md`.
- Private durable object storage behind a storage port; initial low-cost target Cloudflare R2 — `ADR-015-object-storage.md` and `ADR-016-initial-hosting-and-cost-boundary.md`.
- Isolated bounded OCR/image processing — `ADR-013-receipt-processing-boundaries.md` and `ADR-017-ocr-worker-contract.md`.
- Redis Streams consumer group for the initial receipt worker queue — `ADR-019-operational-quality-and-worker-baseline.md`.
- Standard-library JSON logs, liveness/readiness checks, operational alerts, and GitHub Actions quality gates — `ADR-019-operational-quality-and-worker-baseline.md`.

Any change to these choices requires a new ADR before implementation changes are merged.

## Already locked

- USD `local_amount` precision: `0.01`.
- NEW.SYP `local_amount` precision: `0.01`.
- USDT precision: `0.001`.
- Exchange rate precision: `0.001`.
- Rounding: `ROUND_HALF_UP`.
- Receipt amount tolerance: absolute `0.04` in the payment currency.
- Receipt tolerance timing: `QUANTIZED_SNAPSHOT`.
- Backup administrator mode: `EMERGENCY_ONLY`.
- MVP receipt evidence is JPEG/PNG/WEBP only.
- PDF is not processed by the backend; customers with PDF receipts are instructed to send a clear screenshot.
- TOTP is the mandatory primary step-up factor for sensitive admin operations.
- Fees are deducted from USDT delivered, never added to the customer's ShamCash amount.
- `total_amount_user_pays == local_amount`.
- ShamCash is separate from blockchain transfers.
- BEP20 and TRC20 are enabled at launch; TON/ARB/ETH/SOL are disabled and invisible.
- `Order.status` is authoritative for persistent order lifecycle state.
- `expected_version` is required for order transitions.
- `public_order_code` is customer-facing; `internal_order_id` is internal-only.
- Receipt `public_order_code` linkage is the blocking linkage check; other field mismatches are warnings for manual review.
- No automatic order approval.
- No runtime dependency on the legacy repository.
