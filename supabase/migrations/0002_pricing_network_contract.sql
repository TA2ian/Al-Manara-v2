create table if not exists network_configs (
    code text primary key,
    display_name text not null,
    enabled boolean not null default false,
    address_regex text not null,
    requires_memo boolean not null default false,
    min_amount numeric(30, 3) not null,
    max_amount numeric(30, 3) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint network_code_nonempty check (length(btrim(code)) > 0),
    constraint network_display_name_nonempty check (length(btrim(display_name)) > 0),
    constraint network_regex_nonempty check (length(btrim(address_regex)) > 0),
    constraint network_amount_bounds check (min_amount > 0 and max_amount >= min_amount)
);

create table if not exists fee_policies (
    policy_id uuid primary key default gen_random_uuid(),
    network_code text not null references network_configs(code),
    percent numeric(12, 6) not null,
    version text not null,
    effective_at timestamptz not null,
    retired_at timestamptz,
    created_at timestamptz not null default now(),
    constraint fee_policy_percent_check check (percent >= 0 and percent < 100),
    constraint fee_policy_version_nonempty check (length(btrim(version)) > 0),
    constraint fee_policy_window_check check (retired_at is null or retired_at > effective_at)
);

create index if not exists idx_fee_policies_current
    on fee_policies (network_code, effective_at desc, retired_at);

create unique index if not exists uq_fee_policy_version
    on fee_policies (network_code, version);

create table if not exists exchange_rates (
    rate_id uuid primary key default gen_random_uuid(),
    currency text not null,
    rate numeric(30, 3) not null,
    source text not null,
    version text not null,
    captured_at timestamptz not null,
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    constraint exchange_currency_check check (currency in ('NEW.SYP')),
    constraint exchange_rate_positive check (rate > 0),
    constraint exchange_source_nonempty check (length(btrim(source)) > 0),
    constraint exchange_version_nonempty check (length(btrim(version)) > 0),
    constraint exchange_expiry_check check (expires_at is null or expires_at > captured_at)
);

create index if not exists idx_exchange_rates_current
    on exchange_rates (currency, captured_at desc, expires_at);

create unique index if not exists uq_exchange_rate_version
    on exchange_rates (currency, version);

insert into network_configs (code, display_name, enabled, address_regex, requires_memo, min_amount, max_amount)
values
    ('BEP20', 'BEP20', true, '^0x[0-9a-fA-F]{40}$', false, 1, 100000),
    ('TRC20', 'TRC20', true, '^T[1-9A-HJ-NP-Za-km-z]{33}$', false, 1, 100000),
    ('TON', 'TON', false, '.+', true, 0.001, 0.001),
    ('ARB', 'ARB', false, '^0x[0-9a-fA-F]{40}$', false, 0.001, 0.001),
    ('ETH', 'ETH', false, '^0x[0-9a-fA-F]{40}$', false, 0.001, 0.001),
    ('SOL', 'SOL', false, '.+', false, 0.001, 0.001)
on conflict (code) do update set
    display_name = excluded.display_name,
    enabled = excluded.enabled,
    address_regex = excluded.address_regex,
    requires_memo = excluded.requires_memo,
    min_amount = excluded.min_amount,
    max_amount = excluded.max_amount,
    updated_at = now();
