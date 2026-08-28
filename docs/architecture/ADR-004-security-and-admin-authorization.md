# ADR-004: Administrative Authorization and Security Boundaries

## Status

Accepted.

## Decision

Administrative operations are protected by layered authorization rather than callback obscurity.

The runtime model distinguishes:

- `primary_admin_id`
- optional `backup_admin_id`
- active/inactive emergency state
- authenticated admin session
- TOTP step-up confirmation

Sensitive operations require identity, session validity, target/version checks, TOTP confirmation, idempotency, and an append-only audit event.

The backup administrator is emergency-only by default and cannot be activated from an ordinary customer/admin interaction.

### Security boundaries

Telegram input, callbacks, deep links, filenames, images, PDFs, and QR payloads are untrusted.

No user input is passed to `eval`, `exec`, shell commands, dynamic imports, or unparameterized SQL.

File processing is isolated, resource-bounded, and subject to magic-byte validation and a 5 MB limit.

Sensitive data is masked in logs. Secrets are never logged.

### Operational reality

The bot does not claim to protect a compromised host, Telegram account, database, or infrastructure automatically. Incident response includes external credential rotation, session invalidation, audit review, and controlled service shutdown.

## Consequences

The system's most sensitive actions have an explicit authorization boundary that is testable without Telegram UI assumptions.

A compromised or stale callback cannot substitute for authorization or current-version checks.
