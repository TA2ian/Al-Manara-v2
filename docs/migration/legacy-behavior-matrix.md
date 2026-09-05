# Al-Manara Legacy Behavior Matrix

## Purpose

This matrix is the implementation inventory for moving validated user-visible
behavior from `TA2ian/Al-Manara` into Al-Manara v2. It is intentionally a
behavior map, not a file-copy plan. The v2 domain, application, infrastructure,
and Telegram presentation boundaries remain authoritative.

## Source branches reviewed

- `Al-Manara/main` is the reference for currently deployed behavior and the
  canonical source for migration analysis.
- `Al-Manara/development/al-manara-finalization` contains additional QR and
  ShamCash validation work. Its behavior may be assessed selectively; its
  handlers, routers, and adapters are not a runtime dependency.
- `Al-Manara/cleanup/order-wallet-legacy-guard` must not be adopted. It
  reintroduces per-order QR and legacy wallet-guard behavior that the current
  legacy main branch has already retired.

## Classification key

- **KEEP** — implemented in v2; verify it against the legacy behavior before
  changing it.
- **PORT** — a bounded behavior with an existing v2 target contract. Rebuild it
  in that target; do not copy legacy implementation code.
- **REBUILD** — behavior is needed but has no complete v2 contract/runtime
  surface yet.
- **DECIDE** — behavior conflicts with a v2 ADR or needs a product decision
  before implementation.
- **EXCLUDE** — intentionally not part of v2.

## Capability matrix

| Area | Legacy behavior reference | v2 status | Classification | v2 implementation boundary | Required guardrails |
| --- | --- | --- | --- | --- | --- |
| Customer onboarding and terms | `handlers/start.py`, `handlers/legal_navigation_policy.py` | No customer onboarding runtime slice | REBUILD | New Telegram presentation handlers plus application ports | FSM only records the pending input; it cannot own customer/account state. |
| Language and customer profile | `handlers/language_policy.py`, `handlers/profile.py`, `locales/` | No locale/profile runtime slice | REBUILD | New presentation/application boundary | Retain Arabic/English behavior; do not retain legacy fallback storage semantics. |
| Customer order history and status | `handlers/customer_orders_policy.py`, `handlers/customer_navigation_policy.py` | Customer-scoped current-status/history page is available through V2 application, persistence, and Telegram boundaries | KEEP | Customer order-listing service and Telegram handler | Only `public_order_code` and customer-safe summaries are returned; customer identity comes from the authenticated Telegram update. |
| Wallet registration and listing | `handlers/wallets.py`, `handlers/saved_wallets.py` | Wallet domain, repository, register/list/disable services and handler exist | KEEP/PORT | `app/domain/wallet*`, wallet services, `app/runtime/telegram/wallets.py` | Preserve ownership, selected-network validation, verified-wallet immutability, and active-order protection. |
| QR wallet input | `handlers/wallets.py`; finalization QR helpers | V2 accepts QR-oriented registration contracts but has no concrete extraction adapter | PORT | Wallet extraction/normalization port and Telegram adapter | A QR address is first-class; address and QR must match when both are provided. No per-order QR flow. |
| Network surface | Legacy active network settings | V2 launch ADR enables BEP20/TRC20 and defines more networks as disabled | DECIDE | Network registry and customer UI | Do not reintroduce TON. Any expansion beyond BEP20/TRC20 requires an explicit contract decision and tests. |
| Quote, exchange rate, and fees | Amount/currency/payment handlers and services | Quote service, snapshots, Decimal rounding, and persistence adapters exist | KEEP/PORT | Quote/order-creation application services | Preserve v2 financial invariants, including fee deduction from delivered USDT and decimal rounding. |
| Payment method configuration | Payment setup/routing handlers | Payment method and admin payment-account services exist | PORT | Admin payment-account and payment-settings adapters | Preserve immutable order payment snapshots and canonical ShamCash naming. |
| Order creation and active-order safety | Order handlers and database constraints | Atomic order creation, idempotency, versioning, and database contracts exist | KEEP | Order creation service and RPC repositories | No direct handler writes; preserve one active-order and concurrency guarantees. |
| Order state and expiry | Lifecycle services and workers | Versioned transition service exists; no complete runtime scheduling surface | PORT/REBUILD | Transition service, scheduled worker boundary, Telegram handlers | Persistent status is owned only by `Order.status`; server/database time is authoritative. |
| Receipt format and intake | Receipt document/image policies | Image validation/normalization and receipt attempts exist | KEEP/PORT | Receipt input, image policy, and attempt services | JPEG/PNG/WEBP only. PDFs receive screenshot guidance and are never parsed, rendered, or OCR processed. |
| Receipt OCR and review assistance | Receipt processing and verification services | OCR remains a v2 port; verification service and evidence rules exist | PORT | Isolated OCR adapter and receipt orchestrator | Do not invent an OCR provider. A match never auto-approves an order. |
| Receipt retry, locking, and escalation | Receipt retry/lock policies | Reservation, bounded attempts, advisory locking, finalization, and replay exist | KEEP/VERIFY | Receipt attempt persistence/application services | Keep one processing attempt per order and maximum-three-attempt behavior. |
| Admin review, approval, and rejection | Admin review/approval/rejection policies | Review service and handler exist | PORT | Admin review service and transition boundary | Enforce identity, session, expected version, TOTP, idempotency, and audit. |
| Admin closure and fulfillment | Closure and transfer policies | Closure, fulfillment, sessions, listing, and payment accounts are wired | KEEP/PORT | Existing admin services and handlers | Preserve ownership/context/version checks and append-only auditing. |
| Admin tools, notes, messaging, and user management | `handlers/admin_*`, admin services | Only a limited admin runtime slice exists | REBUILD | New application ports and focused handlers | Do not create monolithic admin routers or duplicate callback owners. |
| Maintenance, rate limiting, and anti-abuse | Middleware and operational services | No v2 cross-cutting runtime implementation | REBUILD | Explicit infrastructure/presentation middleware boundary | Keep policy outside domain logic and retain auditable enforcement. |
| Audit logging | Legacy audit service | V2 append-only audit contract exists for covered sensitive actions | KEEP/PORT | Persistence audit adapter and services | Never log secrets, full wallet addresses, or receipt contents. |
| Legacy database initialization | `database.py` and constraint scripts | V2 has versioned SQL migrations/repositories | EXCLUDE | None | Never import or run legacy bootstrap, ALTER, conversion, or startup mutation code. |
| Legacy runtime/router imports | `bot.py`, handlers, middleware | Forbidden by v2 architecture | EXCLUDE | None | The only legacy bridge may be an independently reviewed data migration. |
| Blockchain transfer verification | Legacy transaction-verification helpers | Out of v2 scope | EXCLUDE | None | Administrators retain final authority; do not add explorer verification. |
| PDF receipt processing | Legacy format detection/user guidance | Explicitly excluded from v2 runtime | EXCLUDE | User guidance only | Never add a parser, renderer, or PDF OCR pipeline. |
| Global TXID uniqueness ban | Older transaction conventions | Not required by v2 | EXCLUDE | None | Do not introduce a global reuse ban. |

## Runtime integration audit

This section records what is reachable from the production entrypoint, not merely
what classes or tests exist in the repository.

| Capability | Legacy behavior to preserve | V2 service/contract | Production reachability | Integration action |
| --- | --- | --- | --- | --- |
| Start and main navigation | Guided entry, clear next actions, status-aware menu | No complete application slice | Partial: help text only | Rebuild as a bounded customer navigation router. |
| Customer identity submission | Own Telegram contact, name, ShamCash account, QR, pending state | `CustomerIdentityService` and migration `0041` | Reachable through `/verify`, but currently embedded in the polling runtime | Move to a private-chat identity router with durable conversation state. |
| Customer identity review | Pending queue, QR evidence, approve/reject, customer notification | `CustomerIdentityService.list_pending/approve/reject` and migration `0041` | Not reachable | Add a bounded admin identity router; derive the actor from Telegram and database authorization. |
| Wallet listing/registration/disable | Network selection, address/QR collection, pending verification, saved-wallet controls | Wallet domain, services, repository, and Telegram adapter | Not reachable | Build customer and admin wallet routers; do not duplicate wallet validation in Telegram code. |
| Purchase order creation | Verified wallet, amount, currency, quote, payment instructions | `CreatePurchaseOrderService` and atomic order RPC | Not reachable | Build an order conversation router around the existing service and immutable snapshot contract. |
| Receipt submission | Image-only intake, retry guidance, maximum attempts, admin review handoff | Receipt policies, services, attempt repository, and RPCs | Not composed or reachable | Select concrete adapters, compose once, then add a receipt router. |
| Customer order history | Customer-owned current status and history | Customer order-listing service/RPC | Reachable through `/orders` | Keep, then move unchanged into the customer-orders router. |
| Admin order queue/review | Review queues, version-aware decisions, rejection/clarification | Admin listing/review services and transition RPCs | Not composed or reachable | Supply a concrete production UOW and register an admin-orders router. |
| Fulfillment and closure | Claim, deliver, complete, or close with audit | Fulfillment and closure services/RPCs | Not composed or reachable | Integrate only after admin session/UOW composition is authoritative. |
| Payment accounts and rate settings | Administrator-managed receiving account and exchange rate | Payment-account service/RPC and active exchange-rate persistence | Configured operationally, no Telegram management route | Add focused admin settings routes; never use environment fallbacks. |

## Legacy behavior import rules

For every legacy handler, extract these separately before implementation:

1. **Trigger** — command, button, callback, photo, contact, or text input.
2. **Preconditions** — verified identity, wallet status, order status, admin role,
   session, or confirmation.
3. **State transition** — the durable V2 domain/database change, if any.
4. **User-visible result** — success, retry, empty, rejection, and cancellation
   messages.
5. **Security invariant** — ownership, private-chat requirement, idempotency,
   expected version, and audit.

Only items 1, 2, 4, and the valid parts of 5 are behavior references. Item 3 is
always implemented through the V2 application and persistence contracts. Legacy
FSM keys, SQL, globals, router registration, and dependency setup are never
copied.

## Target Telegram structure

```text
app/runtime/telegram/
  transport.py
  router.py
  shared/
    actor.py
    messages.py
  customer/
    navigation.py
    identity.py
    wallets.py
    orders.py
    receipts.py
  admin/
    sessions.py
    identity_review.py
    wallet_review.py
    order_review.py
    fulfillment.py
    settings.py
```

The production composition root constructs the Supabase client, repositories,
UOW, application services, conversation-state store, and routers exactly once.
Feature routers never construct repositories or execute SQL directly.

## Cleanup gates

A file or dependency is removed when all of the following are true:

- no production composition imports it;
- no retained test verifies still-required behavior through it;
- its replacement has one callback owner and one application boundary;
- repository-wide search shows no runtime dependency on it.

Confirmed cleanup:

- `python-telegram-bot` is removed because production and tests use `aiogram`
  exclusively.

Deferred cleanup:

- existing framework-neutral Telegram adapters remain until their corresponding
  bounded router uses or replaces them;
- the large polling runtime is reduced only after transport, shared policy, and
  customer/admin routers are registered from the new composition;
- `/tmp/al-manara-legacy` remains external reference material and is never added
  to the V2 repository.

## Non-negotiable legacy boundaries

The following legacy patterns must not be copied into v2:

1. Database schema creation, ALTER statements, or data conversion during bot
   startup.
2. Per-order QR assignment or retired wallet compatibility guards.
3. Aliased, compatibility, or duplicate Telegram routers and callback owners.
4. Business configuration sourced from legacy environment-variable fallbacks
   where v2 has a persistent settings/payment model.
5. Direct database access, financial calculations, or order-state mutation in
   Telegram handlers.
6. Legacy FSM values as a source of business status.
7. A runtime dependency on the legacy repository or its modules.

## Delivery order

1. Split polling transport, shared actor/private-chat policy, and router
   registration without changing visible behavior.
2. Move the working order-history and identity-submission routes into bounded
   customer routers and add reachability tests.
3. Complete customer identity review and wallet submission/review.
4. Connect verified-wallet order creation, quote/payment instructions, and
   customer status navigation.
5. Compose receipt infrastructure and connect image-only receipt submission and
   admin order review/fulfillment.
6. Rebuild only retained legacy navigation, language, terms, support, and
   settings behaviors after the transactional flows are complete.
7. Remove dead adapters and dependencies after each replacement passes its
   reachability and no-legacy-import gates.
8. Treat legacy-row data transfer as a separate, reviewable operation after the
   runtime behavior is stable.

## Completion evidence for each migrated behavior

Every PORT or REBUILD item must have:

- an explicit v2 domain/application/persistence or presentation target;
- a regression test covering the observable behavior and security invariant;
- a check that no legacy module is imported;
- an ADR update before deliberately changing any listed v2 boundary.

## Migrated behavior record

### Customer order status and history

The initial customer history slice is now migrated. It provides paginated
customer-owned order summaries and current order status while deliberately
excluding internal order IDs, wallet identifiers/addresses, payment-account
details, and other customers' orders. The total-order count is available even
when the requested page contains no items.

The database contract enforces ownership using the authenticated Telegram user
identity passed by the trusted backend, excludes disabled customers, uses stable
newest-first ordering, and limits RPC execution to `service_role`. Unit and
database contract tests cover identity boundaries, pagination, response
shaping, and RPC access controls.

### Migration sequence

Migration versions are unique through `0041`. The complete V2 chain through the
customer identity-verification contract has been applied to the configured
Supabase project. Runtime startup remains migration-free.