# Receipt Attempt Policy

One image per submission attempt. JPEG, PNG, and WEBP are supported; PDF is outside the MVP.

An order permits at most three sequential attempts. Every failed attempt records a reason. After the third failure the order is escalated to the administrator.

Attempt allocation is serialized per order with a transaction-scoped PostgreSQL advisory lock, preventing concurrent submissions from claiming the same attempt number.
