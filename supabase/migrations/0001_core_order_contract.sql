create extension if not exists pgcrypto;

create table if not exists customer_payment_identities (
    user_id bigint primary key,
    verified_name text not null,
    verified_shamcash_account text not null,
    verified_at timestamptz not null,
    updated_at timestamptz not null default now(),
    constraint customer_payment_identity_name_nonempty check (length(btrim(verified_name)) > 0),
    constraint customer_payment_identity_account_nonempty check (length(btrim(verified_shamcash_account)) > 0)
);

create table if not exists wallets (
    wallet_id uuid primary key default gen_random_uuid(),
    user_id bigint not null,
    network_code text not null,
    address text not null,
    status text not null,
    verified_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint wallet_status_check check (status in ('pending', 'verified', 'rejected', 'disabled')),
    constraint wallet_address_nonempty check (length(btrim(address)) > 0)
);

create index if not exists idx_wallets_user_status on wallets (user_id, status);
create unique index if not exists uq_wallet_verified_address_network
    on wallets (network_code, lower(address))
    where status = 'verified';

create table if not exists orders (
    internal_order_id uuid primary key default gen_random_uuid(),
    public_order_code text not null,
    user_id bigint not null,
    wallet_id uuid not null references wallets(wallet_id),
    network_code text not null,
    wallet_address text not null,
    status text not null default 'draft',
    version bigint not null default 0,
    requested_amount numeric(30, 3) not null,
    fee_percent numeric(12, 6) not null,
    fee_amount numeric(30, 3) not null,
    net_usdt_amount numeric(30, 3) not null,
    payment_currency text not null,
    exchange_rate numeric(30, 3),
    local_amount numeric(30, 2) not null,
    rounding_policy_version text not null,
    customer_verified_name_snapshot text not null,
    customer_shamcash_account_snapshot text not null,
    admin_payment_account_name_snapshot text not null,
    admin_payment_account_number_snapshot text not null,
    admin_payment_qr_file_id_snapshot text not null,
    quote_issued_at timestamptz not null,
    quote_expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint order_public_code_unique unique (public_order_code),
    constraint order_status_check check (status in ('draft', 'awaiting_payment', 'receipt_submitted', 'under_review', 'approved', 'rejected', 'completed', 'expired', 'cancelled')),
    constraint order_version_nonnegative check (version >= 0),
    constraint order_requested_positive check (requested_amount > 0),
    constraint order_fee_nonnegative check (fee_percent >= 0 and fee_percent < 100),
    constraint order_amounts_positive check (fee_amount >= 0 and net_usdt_amount > 0 and local_amount > 0),
    constraint order_quote_window check (quote_expires_at > quote_issued_at),
    constraint order_currency_check check (payment_currency in ('USD', 'NEW.SYP')),
    constraint order_exchange_rate_check check ((payment_currency = 'USD' and exchange_rate is null) or (payment_currency = 'NEW.SYP' and exchange_rate is not null and exchange_rate > 0)),
    constraint order_snapshots_nonempty check (
        length(btrim(customer_verified_name_snapshot)) > 0 and
        length(btrim(customer_shamcash_account_snapshot)) > 0 and
        length(btrim(admin_payment_account_name_snapshot)) > 0 and
        length(btrim(admin_payment_account_number_snapshot)) > 0 and
        length(btrim(admin_payment_qr_file_id_snapshot)) > 0
    )
);

create index if not exists idx_orders_user_created on orders (user_id, created_at desc);
create index if not exists idx_orders_status_updated on orders (status, updated_at);
create index if not exists idx_orders_expiry on orders (status, quote_expires_at);

create table if not exists idempotency_keys (
    user_id bigint not null,
    idempotency_key text not null,
    operation text not null,
    response_json jsonb not null,
    created_at timestamptz not null default now(),
    primary key (user_id, idempotency_key, operation)
);

create table if not exists audit_events (
    event_id uuid primary key default gen_random_uuid(),
    order_id uuid references orders(internal_order_id),
    actor_type text not null,
    actor_id text,
    event_type text not null,
    event_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint audit_actor_type_check check (actor_type in ('system', 'customer', 'admin'))
);

create index if not exists idx_audit_order_created on audit_events (order_id, created_at desc);
