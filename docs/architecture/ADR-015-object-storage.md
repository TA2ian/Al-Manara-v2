# ADR-015: Object Storage Boundary

## Status

Accepted.

## Decision

Durable receipt evidence is stored in object storage rather than PostgreSQL BLOB columns.

PostgreSQL remains the authoritative source for receipt metadata, ownership, lifecycle, verification linkage, retention eligibility, and the opaque object `storage_key`.

## Requirements

The object-storage implementation must support:

- encryption at rest
- private/non-public objects by default
- application-authorized access
- opaque generated object keys
- content-type metadata controlled by the application after real MIME validation
- object deletion
- integrity metadata such as SHA-256
- lifecycle/retention operations without exposing objects publicly

No Telegram user receives a direct permanent public URL to a receipt object.

## Access pattern

```text
Telegram
   ↓
Application authorization
   ↓
Object Storage adapter
   ↓
private object
```

The Domain and Application layers depend on storage ports, not on a concrete storage SDK.

## Upload safety

A file must pass streaming size checks and real MIME/magic-byte validation before it is accepted as durable evidence.

Original user filenames are never used as storage keys.

Receipt files are not executable and are not mounted into an execution environment.

## Temporary versus durable storage

Temporary processing files are managed by the isolated processing subsystem and are deleted after each job, including error and timeout paths.

Only evidence that the application has accepted for durable retention is persisted to object storage.

## Retention

Object lifecycle is governed by `ADR-014`. Object storage lifecycle rules may be used as an additional enforcement layer, but application-level eligibility remains authoritative for business retention.

## Provider selection

The concrete object-storage provider remains an infrastructure implementation decision. The application must not leak provider-specific APIs into Domain or Application contracts.
