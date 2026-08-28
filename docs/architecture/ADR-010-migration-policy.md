# ADR-010: Database Migration Policy

## Status

Accepted.

## Decision

Alembic is the authoritative schema migration tool for Al-Manara v2.

All schema changes must be represented by versioned Alembic migrations. Manual production schema changes are not part of the normal deployment path.

## Migration requirements

Every migration must be validated in CI against a clean PostgreSQL 17 database.

Before production rollout, migrations must also be tested against a representative copy of the current production schema/data where applicable.

Migration failures must fail deployment rather than leaving the application running against an unknown schema state.

## Legacy data migration

Legacy-to-v2 data migration is a separate concern from runtime persistence migrations.

The migration process may read legacy database rows and transform them into v2 structures, but v2 runtime code must never import legacy modules or depend on legacy schema semantics.

The legacy migration process must be independently reviewable, repeatable where practical, auditable, and tested before cutover.

## Rollback

Where a migration is safely reversible, a tested downgrade path should be provided. Irreversible data transformations require an explicit migration plan, backup/restore procedure, and documented cutover strategy rather than pretending that a destructive downgrade is safe.
