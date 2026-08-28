# ADR-009: PostgreSQL and Persistence Baseline

## Status

Accepted.

## Decision

Al-Manara v2 uses **PostgreSQL 17** as its authoritative relational database.

The application persistence stack uses:

- SQLAlchemy 2.x for infrastructure-side database access and mapping.
- Alembic for schema migrations.

## Architectural boundaries

The Domain layer must not import SQLAlchemy, Alembic, PostgreSQL drivers, or ORM models.

Persistence is accessed through application/domain ports implemented by infrastructure repositories.

```text
Presentation
    ↓
Application
    ↓
Domain ports
    ↑
Infrastructure repositories
    ↓
SQLAlchemy 2.x
    ↓
PostgreSQL 17
```

## Data rules

- Financial values use PostgreSQL `NUMERIC` with explicit scale/precision appropriate to their domain contract.
- Identifiers use UUIDs where the domain contract specifies UUID identity.
- Persistent business states are represented by database-backed domain state, not FSM state.
- `Order.version` participates in optimistic concurrency checks.
- Critical lifecycle mutations execute inside database transactions.
- Business uniqueness constraints are enforced by the database as well as validated at the application boundary.
- Foreign keys and status constraints are used to prevent invalid persistence states.
- Audit records are append-only from the application perspective.

## Migration policy

Alembic migrations are the only supported mechanism for evolving the v2 schema.

Migrations must be:

- deterministic
- reviewed
- reversible where technically safe
- tested against a clean database
- tested against representative migrated data before cutover

The legacy repository is not imported by runtime code. Legacy-to-v2 data movement remains a separate migration concern.

## Non-goals

- SQLite is not a production fallback.
- ORM models are not Domain entities.
- JSON blobs are not a substitute for relational constraints on core business state.
