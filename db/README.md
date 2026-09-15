# Database Layer

The PostgreSQL persistence contract is defined by the ordered migrations in `supabase/migrations/`.

## Current policy

- PostgreSQL is the authoritative persistence layer for business state.
- `orders.status` is the authoritative order lifecycle state.
- `orders.version` supports optimistic concurrency.
- Order financial terms are immutable in `order_financial_snapshots`.
- Durable receipt evidence is represented by opaque object-storage metadata in PostgreSQL; binary receipt files are not stored in PostgreSQL.
- Only BEP20 and TRC20 are enabled at launch.
- ShamCash operation references use `shamcash_operation_number` and are never represented as blockchain transaction identifiers.
- `public_order_code` is separate from `internal_order_id`.
- Audit logs are append-only.
- Customer Telegram polling is protected by a database-backed renewable lease,
  so exactly one host may consume updates. The lease expires after missed
  renewals, allowing recovery after an unclean worker stop.

There must be exactly one canonical migration tree. Application repositories and services must enforce the same invariants rather than creating alternate state paths.
