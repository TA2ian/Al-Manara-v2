# ADR-016: Initial Hosting and Cost Boundary

## Status

Accepted.

## Decision

The initial Al-Manara v2 deployment targets a low-cost Render-based environment while preserving provider-independent application contracts.

Render is treated as the initial compute/deployment platform, not as an architectural dependency of the Domain or Application layers.

## Initial infrastructure boundary

```text
Render
├── Web Service / application runtime
├── PostgreSQL 17 (development / initial low-cost environment)
└── Redis-compatible Key Value for ephemeral shared state

Cloudflare R2
└── Durable receipt evidence
```

The exact production service tier is an operational decision and must be reviewed before handling real financial activity. Free infrastructure must not be represented as production-grade durability or availability.

## Important constraints

Render ephemeral filesystem is not durable storage. Receipt evidence must not depend on it for persistence.

Render Free PostgreSQL is suitable for development/testing only and must not be treated as the final production durability strategy because of its lifecycle/backup limitations.

Redis/Key Value is ephemeral by design and is never authoritative for business data.

## Object storage

Cloudflare R2 is the initial low-cost target for durable receipt evidence. The application accesses it through the `ObjectStoragePort` and an infrastructure adapter; no R2-specific API may leak into Domain or Application code.

This permits later migration to another S3-compatible or managed object-storage provider without changing business logic.

## Cost-aware scaling path

The architecture must support the following evolution without Domain/Application redesign:

```text
Initial low-cost deployment
        ↓
Scale application instances
        ↓
Dedicated background workers
        ↓
Stronger PostgreSQL plan / managed database
        ↓
Higher-capacity object storage / infrastructure
```

Scaling a provider must not introduce a second source of business truth.

## Production gate

Before production use involving real customer payments, the deployment must have, at minimum:

- durable PostgreSQL with tested backups/restoration
- private durable receipt storage
- functioning Redis/shared operational state where required
- bounded OCR processing
- monitoring and health/readiness checks
- secret management outside source control
- tested migration and rollback/cutover procedures

The low-cost initial deployment is therefore a cost optimization for development/early operation, not a relaxation of the security and data-consistency contracts.
