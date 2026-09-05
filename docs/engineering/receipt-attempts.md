# Receipt Attempt Contract

The MVP accepts one image per receipt submission attempt. Supported formats are JPEG, PNG, and WEBP; PDF processing is outside the MVP.

Each order has at most three sequential attempts: `1 -> 2 -> 3`. Every failed attempt retains its reason. A failed third attempt escalates to the administrator and closes further customer attempts.

Attempt allocation is serialized per `internal_order_id` with a transaction-scoped PostgreSQL advisory lock. This prevents concurrent submissions from observing the same attempt count and claiming the same attempt number.
