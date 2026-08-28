# Al-Manara v2 Architecture

## Scope

Al-Manara v2 is a Telegram coordination and verification system for customer USDT purchase orders.

The customer pays through ShamCash. The administrator manually sends USDT after approval. The bot never holds USDT and never verifies a blockchain transfer.

## Dependency Direction

```text
Telegram Presentation
        |
        v
Application Services / Commands / Queries
        |
        v
Domain
        ^
        |
Infrastructure implements Domain/Application ports
        |
        v
Database / Object Storage / Processing Workers
```

The Domain layer must not import Telegram, aiogram, database drivers, OCR libraries, or infrastructure implementations.

## Business State Ownership

`Order.status` is the only authoritative source for persistent order lifecycle state.

FSM state is interaction-only and answers: "what input is the bot waiting for now?" It must never represent persistent business status.

## Order Lifecycle

Allowed transitions:

```text
DRAFT
  -> PENDING_PAYMENT
  -> CANCELLED

PENDING_PAYMENT
  -> PAYMENT_SUBMITTED
  -> EXPIRED
  -> CANCELLED

PAYMENT_SUBMITTED
  -> UNDER_REVIEW

UNDER_REVIEW
  -> APPROVED
  -> REJECTED
  -> CLARIFICATION_REQUIRED

CLARIFICATION_REQUIRED
  -> PAYMENT_SUBMITTED
  -> UNDER_REVIEW
  -> CANCELLED

APPROVED
  -> COMPLETED
```

`COMPLETED`, `REJECTED`, `EXPIRED`, and `CANCELLED` are terminal states unless a later business decision explicitly introduces a new transition. No handler may modify `Order.status` directly.

Every transition is performed by one authoritative application service and requires optimistic concurrency through `expected_version`.

## Financial Invariants

- `requested_amount` is the USDT quantity requested by the customer.
- `fee_amount = requested_amount * fee_percent`.
- `net_usdt_amount = requested_amount - fee_amount`.
- `local_amount` is the amount paid through ShamCash.
- `total_amount_user_pays == local_amount`.
- Fees never increase `local_amount`.
- `local_amount` for `NEW.SYP` uses `requested_amount * exchange_rate`.
- `local_amount` for `USD` equals `requested_amount`.
- The exchange rate direction is `1 USD = N NEW.SYP`.
- Financial settings are snapshotted onto the order at creation time.
- Financial calculations use `Decimal` only.
- USD and NEW.SYP `local_amount` precision is `0.01`.
- USDT precision is `0.001`.
- Exchange rate precision is `0.001`.
- Customer-facing financial quantization uses `ROUND_HALF_UP`.
- Receipt amount tolerance is absolute `0.04` in the payment currency and is evaluated against the quantized/snapshotted `local_amount`.

## Payment Terminology

The following names are mandatory:

- `shamcash_operation_number`
- `sender_shamcash_account`
- `recipient_shamcash_account`
- `manual_usdt_transfer_reference`
- `internal_order_id`
- `public_order_code`

`shamcash_operation_number` must never be named `payment_txid`, `blockchain_txid`, or `transaction_hash`.

## Public vs Internal Order Identity

`internal_order_id` is a UUID and never appears in customer-facing messages.

`public_order_code` is random, non-predictable, unique, and is the only order identifier placed in the ShamCash note and shown to the customer.

Receipt linking uses `public_order_code`; it must not expose or derive the internal UUID.

## Receipt Verification — MVP

The MVP accepts receipt evidence as JPEG, PNG, or WEBP images.

PDF processing is explicitly **OUT OF MVP**. The backend does not parse, render, inspect, OCR, or otherwise process PDF receipt files. If the customer has a ShamCash PDF receipt, the user-facing flow instructs them to open the file themselves and send a clear screenshot/image of the receipt.

The supported image path is:

```text
JPEG / PNG / WEBP
        ↓
streaming size limit
        ↓
real MIME / magic-byte validation
        ↓
safe image decode
        ↓
isolated OCR extraction
        ↓
ReceiptData
        ↓
ReceiptVerificationService
```

`ReceiptVerificationService` is the single comparison service for customer-uploaded and admin-uploaded receipt images. Extraction may occur in an isolated processing worker, but comparison rules are identical for both sources.

A missing or mismatched `public_order_code` is a blocking linkage failure. It prevents the receipt from reaching admin review for that order.

Other field mismatches produce explicit field-level warnings. They do not automatically decide the order.

A `MATCH` never means automatic approval. Final order decisions remain manual.

`shamcash_operation_number` may not be successfully reused across two orders.

## Networks

Launch-enabled networks:

- BEP20
- TRC20

Defined but disabled networks may exist in configuration for future expansion:

- TON
- ARB
- ETH
- SOL

Disabled networks must not appear in any customer-facing UI.

Network configuration is data-driven. Network-specific address validation belongs to the network validation boundary and must not be embedded in order handlers.

No blockchain explorer verification is performed for customer payment or wallet registration.

## Wallet Registration

Supported input modes:

1. Text address
2. QR image
3. Wallet share payload

Pipeline:

```text
Input -> Extract -> Normalize -> Validate -> Detect Network -> Match -> Existing Wallet Check -> Verify -> Persist
```

When both address and QR are provided, normalized addresses must match.

A valid QR containing the required address is a first-class registration path and does not require redundant address re-entry.

## Administration

The system supports a primary administrator and optional emergency backup administrator.

Sensitive actions require:

1. identity authorization
2. active admin session
3. target/version validation
4. TOTP step-up confirmation
5. idempotent execution
6. append-only audit event
7. security notification where configured

The backup administrator is `EMERGENCY_ONLY` and is not active merely because an ID exists in configuration.

## Security Boundaries

All Telegram input, callback data, deep links, text, images, and QR payloads are untrusted.

MVP receipt image processing must enforce:

- 5 MB maximum file size
- streaming download limits
- real MIME/magic-byte validation
- safe image decoding limits
- metadata stripping for stored images
- isolated OCR processing
- processing timeouts
- bounded memory
- bounded queues

PDF is not an MVP processing surface.

The application never logs bot tokens, secrets, complete wallet addresses, or receipt contents.

## Transaction and Idempotency Rules

Sensitive operations must be transactional or roll back completely.

Operations such as order confirmation, receipt submission, approval, rejection, completion, and upload must be idempotent.

Stale callbacks must not mutate an already changed order.

## Architectural Non-Goals

This repository must not import runtime code from the legacy `Al-Manara` repository.

The legacy repository is discovery/reference material only. Data migration is the only permitted bridge, implemented separately from runtime application code.
