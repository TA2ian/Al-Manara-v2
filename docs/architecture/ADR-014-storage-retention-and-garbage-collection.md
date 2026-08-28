# ADR-014: Storage Retention and Garbage Collection

## Status

Accepted.

## Decision

Al-Manara v2 separates temporary processing storage from durable receipt evidence storage.

Temporary processing artifacts are cleaned immediately after each processing job, including failure paths. Durable receipt evidence is retained according to an explicit retention policy and is never deleted merely because it is old or because storage pressure occurs.

## Storage model

```text
Telegram upload
    ↓
Temporary processing file
    ↓
validation / decode / OCR
    ↓
Durable object storage when evidence must be retained
    ↓
PostgreSQL metadata/reference
```

Temporary files must use generated opaque identifiers and must not use user-controlled filenames.

## Memory and temporary-file controls

Receipt processing must avoid retaining full uploads unnecessarily in process memory. Downloads use streaming limits and temporary disk-backed files where appropriate.

Every processing job must clean its temporary resources in success, failure, timeout, and cancellation paths.

Workers have explicit bounds for:

- file size
- decoded image dimensions
- memory
- concurrency
- processing time
- queue length
- retries

## Durable object storage

Receipt evidence is stored outside PostgreSQL. PostgreSQL stores metadata and an opaque `storage_key` reference.

Durable evidence objects must:

- use generated non-executable object keys
- be encrypted at rest
- not expose original filenames as storage identifiers
- have access controlled by application authorization
- have integrity metadata such as SHA-256 where required

## Retention policy

Retention is policy-driven and configurable. Each durable evidence record has an explicit retention boundary or an equivalent policy-derived eligibility timestamp.

The system must distinguish retention classes where business requirements require different periods, for example historical completed orders versus abandoned/expired/rejected flows.

A retention worker may delete an object only when all of the following are true:

1. retention has expired
2. the object is not required by an active business/legal retention rule
3. PostgreSQL metadata confirms the object is eligible
4. no active processing/reference operation requires it
5. the deletion is safe to perform transactionally or through an idempotent deletion workflow

If eligibility cannot be established, the worker must not delete the object.

## Retention worker

A dedicated `RetentionWorker` periodically finds eligible objects, rechecks eligibility, deletes them from object storage, and records the deletion outcome in persistent metadata/audit state as required.

Deletion is idempotent: repeated execution after a successful deletion must not corrupt business state.

Storage deletion must never mutate `Order.status`.

## Orphan collection

A separate orphan-detection process may identify object-storage objects that have no valid PostgreSQL reference.

An orphan is not deleted immediately. It enters a grace period, is rechecked against PostgreSQL, and is deleted only if it remains unreferenced.

This protects against races between object upload and database metadata persistence.

## Audit preservation

Deleting a retained receipt image does not erase the historical audit event describing the receipt lifecycle. Audit retention is governed by its own explicit policy.

Logs must never contain the complete receipt image or its sensitive contents.

## Storage pressure

Storage pressure must not cause arbitrary deletion of business evidence.

Operational alerts must fire when storage utilization approaches configured thresholds. Cleanup removes only eligible temporary/orphan/expired objects according to the policy above.

## Non-goals

- No in-memory-only receipt persistence.
- No unbounded temporary-file accumulation.
- No deletion based solely on filename, extension, age, or storage pressure.
- No business-state decisions inside the garbage collector.
