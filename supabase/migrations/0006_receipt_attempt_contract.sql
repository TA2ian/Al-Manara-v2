create table if not exists receipt_attempts (
    attempt_id uuid primary key default gen_random_uuid(),
    order_id uuid not null references orders(internal_order_id) on delete cascade,
    attempt_number smallint not null,
    mime_type text not null,
    telegram_file_id text not null,
    submitted_at timestamptz not null default now(),
    status text not null default 'processing',
    failure_reason text,
    created_at timestamptz not null default now(),
    constraint receipt_attempt_number_check check (attempt_number between 1 and 3),
    constraint receipt_attempt_mime_check check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
    constraint receipt_attempt_file_id_check check (length(btrim(telegram_file_id)) > 0),
    constraint receipt_attempt_status_check check (status in ('processing', 'failed', 'verified', 'escalated')),
    constraint receipt_attempt_failure_reason_check check (
        (status = 'failed' and length(btrim(coalesce(failure_reason, ''))) > 0)
        or (status <> 'failed' and failure_reason is null)
    )
);

create unique index if not exists uq_receipt_attempt_number
    on receipt_attempts(order_id, attempt_number);

create index if not exists idx_receipt_attempts_order_submitted
    on receipt_attempts(order_id, submitted_at desc);

create unique index if not exists uq_receipt_active_processing
    on receipt_attempts(order_id)
    where status = 'processing';
