# Admin Review Transition Boundary

Administrative order review uses a dedicated database transition boundary.

The generic `transition_order_idempotent` path remains separate from admin-session authorization. Admin review requires the authoritative admin actor, an active session bound to that actor, the expected order version, and an allowed review transition (`UNDER_REVIEW` to `APPROVED`, `REJECTED`, or `CLARIFICATION_REQUIRED`).

The database boundary is the final authorization point. It resolves the administrator and validates the explicit session before idempotency replay, then atomically reserves/replays the idempotency key and locks the order before the version/state checks and mutation. Telegram and application-layer checks are defense-in-depth only.

A successful transition writes one immutable audit record and finalizes the same database idempotency record. Replays return the committed result without applying a second state transition or audit event. A revoked or expired session cannot replay a privileged result.

No user-supplied text is executed as a command. Review reasons are data, normalized and bounded before being passed to the persistence boundary, and persisted as audit/event metadata only.
