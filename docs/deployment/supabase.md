# Supabase Deployment Contract

## Target project

Al-Manara v2 uses the following Supabase project as its database target:

- Project name: `AI Manara`
- Project reference: `oiszcfqfrltwcnwgnzka`
- Region: `ap-southeast-1`
- PostgreSQL major version: 17

The project reference is configuration, not a secret. Database credentials, service-role keys, and other secrets must never be committed.

## Migration source of truth

Database migrations live under `db/migrations/` and are the canonical SQL history for this repository.

`supabase/config.toml` pins the project reference for Supabase CLI workflows. It does not contain credentials.

## Safe deployment sequence

```text
1. Inspect target database
2. Verify migration history
3. Verify public schema state
4. Apply pending migrations only
5. Inspect resulting constraints/indexes/triggers
6. Run database invariant tests
7. Run security review
```

Never apply the initial schema blindly to an unknown database.

## Environment separation

Development/staging and production databases must use separate Supabase projects or otherwise isolated database environments. Production credentials must not be used for local development.

## Security boundary

The application must connect through the repository/infrastructure layer. Domain and Application code must not import Supabase SDK types or depend on Supabase-specific APIs.

Supabase is the managed PostgreSQL provider. PostgreSQL remains the persistence contract.

## Storage boundary

Receipt evidence is not stored in PostgreSQL as binary application data. The database stores metadata and opaque storage references. Durable object storage remains behind `ObjectStoragePort`.

## RLS decision

RLS is not being used as a substitute for the application's authorization model. The bot has one controlled backend actor model, and all sensitive authorization remains in the Application layer. If direct client access to Supabase is introduced later, RLS becomes mandatory before exposing any table to that client.

## Current status

The repository is configured for project `oiszcfqfrltwcnwgnzka`. The initial migration must still be executed and verified against the actual remote database before this deployment is considered complete.
