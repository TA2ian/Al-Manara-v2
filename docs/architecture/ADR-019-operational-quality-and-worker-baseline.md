# ADR-019: Operational Quality and Worker Baseline

## Status

Accepted for the initial v2 implementation baseline.

## Context

The existing v2 ADR set establishes the runtime, persistence, storage, receipt-processing, and deployment boundaries. This ADR closes the remaining implementation-level choices that must not be selected silently by application code.

## Decisions

### Receipt worker queue

Receipt-processing jobs use Redis Streams with a consumer group. Redis is operational and ephemeral only; PostgreSQL remains authoritative for receipt submissions, processing status, order status, and audit history. Queue capacity, per-order single-active-job enforcement, retry count, timeout, and backoff are bounded by application policy.

A worker is a separate process boundary. It receives an opaque validated-image reference and immutable job metadata, returns structured extraction data, and never writes Orders, Settings, Wallets, or Audit Logs directly.

### Structured logging

Application logs use a standard-library JSON formatter emitted to stdout/stderr for collection by the runtime platform. Every business event includes safe correlation fields where available: event name, user ID, order ID, wallet ID, actor type, action, state transition, and error category.

Secrets, Bot Tokens, complete wallet addresses, ShamCash account values, receipt contents, original filenames, and raw OCR text are excluded or masked. Logging is diagnostic only and is never an authority for business state.

### Health and monitoring

The runtime exposes separate liveness and readiness checks. Readiness verifies required authoritative dependencies and fails closed for security-sensitive operations when shared controls are unavailable. Operational alerts cover unauthorized admin attempts, processing failures, queue saturation, database errors, storage failures, and resource pressure.

Monitoring and alerting may identify incidents but must not transition orders, approve payments, or change settings.

### Continuous integration

GitHub Actions is the CI runner. The required quality gates are:

- Python 3.13 compatibility
- dependency installation from the v2 project manifest/lock policy
- Ruff lint and format validation
- mypy checks for typed Domain and Application contracts
- pytest unit, integration, lifecycle, router, security, and migration suites
- dependency and secret scanning
- architecture-boundary checks preventing Domain imports of Telegram, ORM, OCR, and storage SDKs
- a clean-database migration test and representative migration dry run

A failed required gate blocks merge. CI does not import or execute the legacy repository.

## Consequences

The first implementation can be developed locally with containerized PostgreSQL and Redis-compatible services while preserving the same contracts used by the initial Render deployment. Redis loss cannot rewrite business truth. Additional monitoring providers or a different queue implementation require a new infrastructure decision and must preserve these boundaries.

## Related decisions

- ADR-007 — Python 3.13 runtime
- ADR-008 — aiogram 3.31.0 boundary
- ADR-009 — PostgreSQL 17 and SQLAlchemy/Alembic persistence
- ADR-012 — Redis shared ephemeral state
- ADR-013 and ADR-017 — isolated receipt processing and OCR worker contract
- ADR-015 and ADR-016 — private object storage and initial Render/R2 boundary
