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

**TOTP is the primary and mandatory step-up factor for sensitive administrative actions in the MVP.** A generic second button or callback confirmation is never a substitute for TOTP.

Sensitive operations require:

1. authorized administrator identity
2. active admin session within the configured inactivity timeout
3. target identity and current-version validation
4. fresh TOTP step-up confirmation bound to the intended action/target
5. idempotent execution
6. transactional state change
7. append-only audit event
8. security notification where configured

The backup administrator is emergency-only by default and cannot be activated from an ordinary customer/admin interaction.

### Security boundaries

Telegram input, callbacks, deep links, filenames, images, and QR payloads are untrusted.

No user input is passed to `eval`, `exec`, shell commands, dynamic imports, or unparameterized SQL.

MVP receipt evidence is image-only. File processing is isolated, resource-bounded, and subject to magic-byte validation and a 5 MB limit.

Sensitive data is masked in logs. Secrets are never logged.

### Operational reality

The bot does not claim to protect a compromised host, Telegram account, database, or infrastructure automatically. Incident response includes external credential rotation, session invalidation, audit review, and controlled service shutdown.

## Consequences

Sensitive administrator actions have one explicit step-up mechanism in the MVP: TOTP.

A compromised or stale callback cannot substitute for authorization, a fresh session, TOTP, or current-version checks.

Future replacement/addition of an authentication factor requires an explicit security ADR and must not silently weaken the sensitive-action contract.
