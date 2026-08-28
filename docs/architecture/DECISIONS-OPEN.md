# Open Decisions Before Implementation

This document is the implementation gate. No production implementation may silently choose a value listed here.

## Business decisions

### 1. Financial precision

Decision:

- USD `local_amount`: 0.01
- NEW.SYP `local_amount`: 0.01
- USDT: 0.001
- Exchange rate: 0.001

All monetary values use `Decimal` with explicit precision and quantization policy.

### 2. Rounding mode

Decision:

- `ROUND_HALF_UP`

This is the explicit policy for customer-facing financial quantization.

### 3. Receipt amount tolerance

Status: pending explicit value.

The tolerance must define the allowed receipt-vs-expected amount difference. The policy may use an absolute amount, percentage, or both.

### 4. Tolerance timing

Decision:

- `QUANTIZED_SNAPSHOT`

Receipt tolerance is evaluated against the already-quantized/snapshotted `local_amount`.

### 5. Backup administrator mode

Decision:

- `EMERGENCY_ONLY`

The backup administrator is inactive during normal operation and may be activated only through the defined emergency procedure. The mere presence of a backup administrator ID/configuration does not grant normal operational authority.

## Engineering decisions

The following must be proposed and then explicitly accepted before implementation is considered architecture-locked:

- Python version.
- aiogram version.
- PostgreSQL version.
- Migration tooling.
- Redis/shared-state implementation.
- Object storage implementation.
- OCR engine and isolation strategy.
- Worker/queue implementation.
- Container/runtime deployment model.
- Structured logging and monitoring stack.
- CI tooling and quality gates.

## Already locked

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
