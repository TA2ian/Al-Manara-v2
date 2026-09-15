# Al-Manara → v2 Migration Gap Analysis

## Status

Working baseline for `integration/al-manara-migration`.

## Objective

Move the required, validated behavior of the current Al-Manara implementation into Al-Manara-v2 without copying the legacy runtime architecture. The v2 architecture remains authoritative for new runtime code.

## Verified current Al-Manara capabilities

The current `main` branch contains materially more runtime behavior than the v2 foundation, including:

- Customer onboarding, Arabic/English navigation, legal/terms flow, profile and account handling.
- Wallet creation/selection, QR validation, saved wallets, wallet verification and protections for verified wallets.
- Sequential order lifecycle with database-level active-order protection and explicit state-transition constraints.
- Quote/order amount policy, exchange-rate handling, service-fee and network-fee calculations, and immutable payment/order snapshots.
- ShamCash payment methods with administrative setup/validation and canonical payment-method identifiers.
- Customer payment-currency selection and payment-method routing.
- Receipt document policy and image receipt processing policy.
- PDF evidence handling as format detection only; PDF parsing/rendering/OCR is not part of the active path. Users are directed to submit a screenshot as an image.
- Receipt verification assistance with an administrator remaining authoritative for payment decisions.
- Receipt retry/concurrency protections and database constraints.
- Administrative approval, rejection, payment confirmation, order listing/search, transfer, notes, maintenance, tools and user-management policies.
- Administrative order closure with session/ownership/context guards and regression coverage.
- Customer order history/status flows.
- Rate limiting and anti-abuse controls.
- Audit logging.
- PostgreSQL persistence and database-level invariants.
- Runtime keyboard/callback routing and customer/admin navigation separation.

## Verified v2 foundation

The v2 `integration/main-canonical-v2` branch is substantially ahead of v2 `main` and already contains a clean domain/application/infrastructure implementation for orders, quotes, wallets, receipt intake/processing/verification, receipt-attempt persistence, concurrency, database contracts, and unit/database tests. It is therefore the correct v2 implementation baseline for the migration work, rather than rebuilding those 168 commits from scratch.

The v2 architecture establishes:

- Order lifecycle separated from Telegram FSM state.
- Versioned order updates with optimistic concurrency.
- Immutable order financial snapshots.
- Explicit PaymentMethod and payment snapshot concepts.
- First-class customer payment identity.
- Image-only MVP receipt evidence.
- Isolated, bounded receipt processing.
- Append-only audit requirements.
- Explicit administrative authorization/security boundary.
- PostgreSQL persistence as authoritative runtime state.
- Alembic as the authoritative schema migration mechanism.
- Data-only legacy migration boundary; v2 runtime must not import legacy modules.
- Data-driven network registry.
- Explicit rounding/tolerance contracts.
- Redis for shared ephemeral state where required.

## Important reconciliation findings

### 1. v2 scope documents are behind current Al-Manara behavior in some areas

The v2 ADRs describe a narrower launch surface in several places. For example, the v2 network ADR documents BEP20/TRC20 as launch-enabled, while current Al-Manara documents BEP20, TRC20, ARB, SOLANA, ETH and POLYGON as the active customer network list. This must be reconciled before the network surface is finalized in v2.

### 2. TON must not be resurrected

The migration must not reintroduce the previously removed first-generation TON path or logic coupled exclusively to it. Current Al-Manara's active network list does not include TON.

### 3. PDF processing remains screenshot-based

Current Al-Manara and the v2 MVP direction agree on the runtime boundary: PDF content is not parsed/rendered/OCR'd in the active receipt flow. PDF handling is format detection plus user guidance to submit an image screenshot.

### 4. Time handling

Order processing/deadline behavior must remain duration-based and server/database authoritative. Customer device clock, GPS location and timezone must not control stored processing duration or security decisions.

### 5. TXID reuse restriction is not a migration requirement

The migration must not introduce a global rule that rejects reuse of a blockchain TXID. Network-aware validation may still be required where applicable, but there is no product requirement to block repeated TXID values globally.

### 6. PostgreSQL runtime contract must be preserved

Current Al-Manara uses PostgreSQL through `DATABASE_URL` and does not require Supabase as a runtime dependency. v2's repository/migration architecture must preserve the PostgreSQL runtime contract unless an explicit architecture decision changes it.

## Migration classification

| Area | Action | Notes |
|---|---|---|
| Order domain/lifecycle | REBUILD in v2 | Preserve validated behavior; use v2 versioned state transitions and repositories/services. |
| Financial calculations | REBUILD/VERIFY | Preserve current monetary behavior and snapshots; reconcile any precision/fee differences with v2 contracts. |
| Network registry | RECONCILE then REBUILD | Current supported list is broader than the v2 launch ADR. TON remains excluded. |
| Wallets/QR/verification | REBUILD | Preserve validation and verified-wallet immutability/active-order protections. |
| Payment methods | REBUILD | Preserve canonical ShamCash configuration, snapshots and setup flow. |
| Receipt evidence | REBUILD/EXTEND | Keep image-only runtime boundary and durable evidence metadata. |
| Receipt retry/concurrency | KEEP/VERIFY/EXTEND | v2 already has a dedicated receipt-attempt implementation; compare it against current behavior before extending. |
| Admin approval/rejection | REBUILD | Preserve authoritative human decision boundary. |
| Admin closure | REBUILD | Preserve ownership, context/version and lifecycle guards. |
| Admin tools/settings/maintenance | REBUILD selectively | Move business behavior, not legacy handler structure. |
| Customer navigation | REBUILD | Re-express in the v2 Telegram layer. |
| Keyboard/callback routing | REBUILD | Preserve behavior while preventing stale/ambiguous callback paths. |
| Audit logs | REBUILD | Use v2 append-only audit contract. |
| Rate limiting/anti-abuse | REBUILD | Keep as cross-cutting v2 infrastructure. |
| PDF parsing/OCR | DROP | Not part of current active PDF path. |
| Legacy TON path | DROP | Explicitly excluded. |
| Global blockchain TXID uniqueness/reuse ban | DROP | Not required. |
| Legacy database bootstrap/mutation logic | DROP | Replace with v2 migrations/repositories. |

## Next implementation gate

The next task is to inventory the exact v2 schema/contracts and map each current Al-Manara handler/service/policy to a v2 domain/application/infrastructure target. Any conflict between current behavior and an existing v2 ADR must be resolved by an explicit contract decision and regression test rather than silently selecting one implementation.

## Completion criteria for this migration stage

- Every current customer/admin capability is classified.
- Every capability marked REBUILD has a v2 target contract.
- Excluded legacy behavior is explicitly listed so it cannot return accidentally.
- Conflicting v2 ADRs are identified before code migration.
- The migration branch contains the analysis without changing v2 `main`.
