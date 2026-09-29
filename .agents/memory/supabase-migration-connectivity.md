---
name: Supabase migration connectivity
description: Reliable migration path when direct database access is unavailable from this Replit environment.
---

Use the Supabase CLI linked to the target project to apply checked-in migrations when direct PostgreSQL connections are unavailable. Avoid relying on the Supabase Management database-query endpoint for migration execution because it may reject the available access token.

**Why:** The environment could resolve only an IPv6 database endpoint and direct `psql` did not provide a usable connection, while the official CLI successfully connected and applied the migration.

**How to apply:** Link with the target project reference and database password supplied through Replit Secrets, run the official migration push command, then verify the remote migration list. Never print credentials or connection strings.