-- A customer may have at most one non-terminal order at a time.
-- Telegram interaction state is not authoritative; this database constraint is the
-- concurrency-safe business guard for parallel /buy attempts.
-- Terminal orders remain available in history and do not block a new operation.

create unique index if not exists orders_one_active_per_user_uq
    on orders(user_id)
    where status in (
        'DRAFT',
        'PENDING_PAYMENT',
        'PAYMENT_SUBMITTED',
        'UNDER_REVIEW',
        'APPROVED',
        'CLARIFICATION_REQUIRED'
    );
