# Admin Review Transition Boundary

Administrative order review uses a dedicated database transition boundary.

The generic `transition_order_idempotent` path remains separate from admin-session authorization. Admin review requires the authoritative admin actor, an active session bound to that actor, the expected order version, and an allowed review transition (`UNDER_REVIEW` to `APPROVED`, `REJECTED`, or `CLARIFICATION_REQUIRED`).

Authorization is checked before state mutation. The order is locked before the version/state checks and transition. The database boundary is the final authorization point; Telegram and application-layer checks are defense-in-depth only.

No user-supplied text is executed as a command. Review reasons are data and are persisted as bounded event metadata.
