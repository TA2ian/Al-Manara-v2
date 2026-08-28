# Al-Manara Legacy Repository Audit

- Audit scope: `TA2ian/Al-Manara`, branch `main`
- Target: `TA2ian/Al-Manara-v2`, branch `agent/al-manara-v2-rebuild`
- Audit mode: read-only discovery; no legacy code or business logic is imported
- Audit date: 2026-08-28

## Executive decision

The legacy repository must not be used as the implementation base for Al-Manara v2. It is a discovery and data-migration source only. The v2 implementation must remain independent and must not import legacy handlers, FSM states, callbacks, guards, services, or business logic.

The existing v2 repository already contains architecture decisions that align with the master specification. This document records the legacy findings that must be respected before production implementation begins.

## 1. Repository inventory

The legacy repository contains 202 tree entries and 193 blobs, including:

- 15 root files
- 39 handler modules
- 27 service modules
- 87 test files
- 8 keyboard modules
- 6 middleware modules
- 2 locale files
- 8 attached image assets
- runtime, database, deployment, and CI files

The repository is a substantial Python Telegram bot, not a minimal prototype. Its size and number of policy modules increase the risk of silently carrying legacy assumptions into a rewrite.

## 2. Existing architecture

The legacy code has useful separation attempts: aiogram-based Telegram handling, async PostgreSQL access, service modules, database constraints, media-security helpers, rate limiting, audit logging, and a broad regression suite.

However, the boundaries are not suitable as the v2 domain boundary:

- Database access and schema creation are concentrated in `database.py` and related constraint modules.
- Business policy is spread across many handler and policy modules.
- Presentation, persistence, authorization, and business decisions are coupled across parts of the handler/service surface.
- `states.py` contains interaction states that reflect legacy flows and must not become persistent business state in v2.
- Financial fields such as `requested_amount_usdt`, `amount_usdt`, `base_amount`, `fee_amount`, and `total_amount` do not constitute the v2 `OrderFinancials` contract without an explicit mapping.

The v2 dependency direction must remain `Presentation -> Application -> Domain`, with Infrastructure implementing ports and the Domain free of Telegram, aiogram, database drivers, OCR libraries, and storage SDKs.

## 3. Confirmed business-flow discrepancies

### 3.1 Order lifecycle

The legacy lifecycle uses statuses including:

```text
pending -> waiting_payment -> receipt_received -> payment_confirmed -> completed
```

The v2 lifecycle is:

```text
DRAFT -> PENDING_PAYMENT -> PAYMENT_SUBMITTED -> UNDER_REVIEW -> APPROVED -> COMPLETED
```

The old approval path can move a pending order to a payment-waiting state and deliver payment details after administrative approval. That is not the v2 flow. In v2, the order receives its ShamCash payment instructions before payment submission; administrative approval occurs only after review and remains manual.

No legacy transition table, rollback helper, or direct status update may be copied into v2. All persistent transitions must go through the new authoritative transition service with actor, reason, and expected version.

### 3.2 Blockchain terminology and automatic approval

The legacy FSM includes a `waiting_typing_txid` state, and legacy transfer/fulfillment surfaces contain blockchain/TXID terminology. The legacy test inventory also includes trusted-customer auto-approval behavior.

These are prohibited in the v2 MVP:

- No blockchain TXID is requested or verified.
- No chain verifier or external blockchain API is used.
- `manual_usdt_transfer_reference` is optional documentation entered by the administrator after an external manual transfer; it does not prove or automatically complete a transfer.
- No order is automatically approved, including for trusted customers or a matching receipt.

### 3.3 Receipt evidence

The legacy repository includes receipt document/media policies, PyMuPDF in its dependency list, and tests around document/media handling. The v2 MVP is image-only: JPEG, PNG, and WEBP. PDF is not processed by the backend and must not re-enter the current flow through a compatibility path.

v2 must provide one `ReceiptVerificationService` for both `customer` and `admin_verified` evidence sources. The source is audit data, not a separate comparison algorithm. Missing or incorrect `public_order_code` blocks linkage; other mismatches become explicit review flags and never create an automatic decision.

### 3.4 Financial semantics

The v2 financial contract is authoritative:

```text
fee_amount = requested_amount * fee_percent
net_usdt_amount = requested_amount - fee_amount
USD local_amount = requested_amount
NEW.SYP local_amount = requested_amount * exchange_rate
total_amount_user_pays = local_amount
```

The fee is deducted from USDT delivered after approval. It is never added to the customer's ShamCash amount. Legacy financial columns must be mapped into a new immutable snapshot; they must not be renamed and reused without semantic verification.

### 3.5 Wallets and networks

The legacy code has wallet, QR, saved-wallet, and network validation surfaces. These are discovery evidence only. The v2 implementation must unify text, QR, and wallet-share payload validation, require explicit network selection, compare QR and text after normalization, and expose only BEP20 and TRC20 in the MVP. TON, ARB, ETH, and SOL must remain invisible.

## 4. Administration and security findings

The legacy configuration supports an administrator ID allowlist and runtime settings surfaces. v2 must not carry this authorization model forward as-is.

The v2 authorization boundary requires:

- `primary_admin_id` and optional `backup_admin_id` configured outside normal Telegram UI
- `EMERGENCY_ONLY` as the safe default for the backup administrator
- fresh admin session validation and rate limiting
- mandatory TOTP step-up for sensitive operations
- target and expected-version checks for confirmations
- append-only audit events with actor, action, target, old value, new value, reason, and confirmation context
- no deletion of historical orders, receipts, or audit records when a user or wallet is disabled

The legacy media-security and rate-limit code are useful evidence, but they do not waive the v2 requirements for streaming size limits, magic-byte checks, bounded decoding, safe re-encoding, opaque storage IDs, isolated processing, queue limits, timeouts, and per-user cooldowns.

## 5. Test inventory assessment

The legacy repository has 87 test files covering administration, wallets, order lifecycle, receipts, media security, currencies, settings, and release gates. The suite is valuable as a regression inventory, but it cannot be copied wholesale because some tests encode prohibited behavior, including legacy fulfillment/TXID, trusted-customer auto-approval, document support, and old lifecycle semantics.

v2 tests must be authored against the new invariants, especially:

- fee deduction and local-amount comparison
- immutable financial and payment snapshots
- expected-version and idempotent transitions
- public-code linkage
- customer and admin receipt evidence through the same service
- manual-only approval and completion
- QR-only, text, and wallet-share validation
- file boundaries and processing isolation
- admin authorization, TOTP step-up, stale callbacks, and audit logging
- migration dry-run, reconciliation, rollback, and duplicate handling

No claim is made that the legacy suite is a release approval for v2. v2 has no production implementation yet, and its tests must be independent.

## 6. Migration boundaries

Migration is data-only and independent from the v2 application. The mapping must cover users, ShamCash payment identities, wallets, orders, payment methods, receipts, audit records, and settings.

The following records require quarantine or explicit manual review rather than blind conversion:

- orders whose old status does not establish a reliable v2 status
- records with ambiguous financial column semantics
- duplicate operation numbers or wallets
- missing or conflicting payment snapshots
- receipts without a reliable order linkage
- records that imply blockchain verification or automatic approval

Required migration controls are read-only discovery, mapping review, backup, dry run, before/after counts, reconciliation, freeze-based cutover, and a tested rollback plan. Legacy application code is not part of the migration artifact.

## 7. Go/no-go gate

Implementation may proceed only after the v2 engineering decisions are explicitly accepted and the following are true:

- this audit remains committed before production code
- no legacy runtime dependency is added
- v2 domain contracts and invariants are locked
- migration mappings and ambiguous-record policy are documented
- the new persistence and processing boundaries are selected
- tests are written for v2 behavior rather than copied from legacy behavior

## Sources

- Legacy repository: `TA2ian/Al-Manara`, branch `main`
- Target repository: `TA2ian/Al-Manara-v2`, branch `agent/al-manara-v2-rebuild`
- Product specification: `Al-Manara — Master Prompt v2`
