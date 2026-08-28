# ADR-018: Domain Persistence Contract

## Status

Accepted.

## Purpose

This ADR defines the first authoritative persistence contract for Al-Manara v2. It establishes ownership of state, immutable financial snapshots, identity boundaries, uniqueness constraints, and optimistic concurrency before implementation of ORM models.

## Authoritative aggregates

### User

`User` is the authoritative customer identity record. Customer payment identity is owned by the user and represents the verified ShamCash identity used for future receipt comparisons.

Customer payment identity fields:

- `verified_name`
- `verified_shamcash_account`
- verification metadata/timestamps as required

Disabling a user does not erase historical order evidence.

### Wallet

`Wallet` is the authoritative customer receiving-wallet record.

Wallet lifecycle:

```text
PENDING → VERIFIED
PENDING → REJECTED
VERIFIED → DISABLED
```

A verified wallet may be selected by later orders. Wallet state is not duplicated into FSM or Telegram messages.

A wallet belongs to one user. Address identity is scoped by network; a unique normalized address/network constraint prevents accidental duplicate registration while allowing the same address string on distinct future networks where the network semantics differ.

### Wallet Verification

`WalletVerification` records an attempt/request and its status. It does not become the source of truth for whether a wallet is currently usable; current usability comes from `Wallet.status`.

### Order

`Order.status` is the sole authoritative order lifecycle state.

`Order.version` is mandatory and is incremented on every successful authoritative mutation relevant to optimistic concurrency.

No handler or repository caller may assign arbitrary status values outside the Order transition service.

### Receipt Submission and Evidence

A `ReceiptSubmission` represents one customer/admin evidence submission attempt for an order. One attempt contains exactly one receipt image in MVP.

`ReceiptEvidence` represents the stored image object and its storage metadata.

`ReceiptData` and `ReceiptVerificationResult` are structured outputs of the receipt verification pipeline and are persisted as evidence/results, not as a replacement for `Order.status`.

### Settings and network configuration

Settings are authoritative configuration state. Network availability is data-driven through `NetworkConfig`.

At launch only `BEP20` and `TRC20` are enabled. `TON`, `ARB`, `ETH`, and `SOL` may exist as disabled configuration records but must not appear in user-facing selection flows while disabled.

## Order financial snapshot

Financial values are immutable snapshots once an order is created:

- `requested_amount`
- `fee_percent`
- `fee_amount`
- `net_usdt_amount`
- `payment_currency`
- `exchange_rate`
- `local_amount`
- rounding policy identifier/version
- relevant network configuration identifier/version

The snapshot is the source of truth for the order's quoted financial terms. Later Settings changes do not mutate it.

The invariant is:

```text
fee_amount = requested_amount × fee_percent
net_usdt_amount = requested_amount - fee_amount
```

`local_amount` is based on `requested_amount`, never on `net_usdt_amount` and never on `requested_amount + fee_amount`.

For `USD`:

```text
local_amount = requested_amount
```

For `NEW.SYP`:

```text
local_amount = requested_amount × exchange_rate
```

The configured precision and `ROUND_HALF_UP` policy are applied consistently.

## Payment identity and receipt constraints

`shamcash_operation_number` is a ShamCash operation reference and must never be represented with blockchain transaction terminology.

A successfully linked ShamCash operation number may not be reused for another successful order. Database-level uniqueness must back the application-level check.

`public_order_code` is the customer-visible order identifier. It is random, non-predictable, unique, and separate from `internal_order_id`.

`internal_order_id` never appears in customer-facing instructions or receipt notes.

## Receipt linkage invariant

A receipt must be linked to the intended order by the matching `public_order_code` before it can enter the normal administrator review path.

Missing or mismatched `public_order_code` is a blocking linkage failure.

Other field mismatches (sender name/account, recipient data, amount, currency, date) are comparison results/warnings and do not automatically decide approval or rejection.

## Administrative state

Administrative authorization is external configuration plus runtime session/step-up verification. Administrator identity is not inferred from Telegram message content.

`primary_admin_id` and `backup_admin_id` are not editable through ordinary bot flows.

Sensitive actions require TOTP step-up confirmation and an auditable confirmation identifier.

## Audit log

`AuditLog` is append-only from the application's perspective. It records sensitive state/configuration mutations with actor, action, target, old/new values or states, timestamp, and metadata as appropriate.

Audit records are never used as a substitute for the current authoritative entity state.

## Optimistic concurrency

All authoritative order transitions require:

```text
order_id
 target_status
 actor
 reason
 expected_version
```

The persistence layer must perform an atomic version/state check. If the expected version no longer matches, the operation fails with `ConflictError` and must not mutate the order.

The same principle applies to other sensitive mutable resources where concurrent administrator/worker operations can conflict.

## Referential safety

Historical orders, receipt evidence, verification records, and audit records must survive customer disable/archive operations.

Customer deletion therefore uses a policy-driven soft-delete/disable/archive mechanism rather than destructive cascading deletion of financial history.

Foreign keys must use explicit delete behavior. Cascading deletion of historical financial evidence is prohibited.

## Transaction boundaries

Creation and mutation workflows that modify multiple authoritative records must execute transactionally. A failed transaction must not leave a half-created order, financial snapshot, receipt linkage, or state transition.

External side effects such as Telegram notification or object-storage deletion must not be mistaken for database transactions; they require idempotent/outbox-style coordination where reliability requires it.

## Naming invariant

The following names are reserved and must be used literally for their meanings:

- `shamcash_operation_number`
- `sender_shamcash_account`
- `recipient_shamcash_account`
- `manual_usdt_transfer_reference`
- `internal_order_id`
- `public_order_code`

`payment_txid`, `blockchain_txid`, and `transaction_hash` must not be used for the ShamCash operation number.
