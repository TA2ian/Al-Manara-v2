# ADR-012: Redis Shared Ephemeral State

## Status

Accepted.

## Decision

Al-Manara v2 uses Redis as shared, ephemeral operational infrastructure.

Redis is not an authoritative source of business state and must never become a second store for persistent Order, Wallet, Receipt, Verification, Settings, financial snapshot, or Audit Log state.

## Approved uses

Redis may be used for:

- distributed rate-limit counters
- short-lived idempotency keys
- short-lived administrative/session state where shared process state is required
- short-lived coordination/locks where the application requires them and PostgreSQL transaction/locking semantics alone are insufficient
- worker/queue coordination if the selected queue implementation uses Redis

## Authoritative data remains PostgreSQL

The following remain exclusively authoritative in PostgreSQL:

- `Order.status`
- `Order.version`
- financial snapshots
- wallet verification state
- receipt and verification records
- customer identity data
- settings and exchange-rate state
- append-only audit records

Redis expiration, eviction, restart, or temporary unavailability must never silently alter business truth.

## Rate limiting

Rate limiting uses Redis/shared state so limits remain effective across multiple application processes/workers.

Default user-facing limits remain:

- 20 general messages/minute/user
- 5 new orders/hour/user
- 5 consecutive invalid wallet-address attempts → 15-minute wallet-add cooldown
- 10 receipt/image uploads/hour/user
- 5 consecutive receipt submissions that cannot be linked to the current order → temporary order restriction according to the anti-abuse policy

Administrative operations use separate administrator-specific limits.

## Idempotency

Short-lived idempotency records may be stored in Redis to absorb duplicate Telegram deliveries or repeated UI actions, but critical uniqueness and state correctness must also be enforced transactionally in PostgreSQL.

Redis must never be the sole protection against duplicate financial/business mutations.

## Failure policy

Redis failure must fail closed for security-sensitive operations where the application cannot safely enforce the required shared control. The application must not silently fall back to per-process in-memory counters for production rate limits.

Where a Redis-backed operational feature is unavailable, the application should return a bounded, explicit service-unavailable response rather than pretending the protection remains active.

## Data lifetime

Redis entries are ephemeral and must have explicit TTLs appropriate to their purpose. Persistent business history must never depend on Redis retention.
