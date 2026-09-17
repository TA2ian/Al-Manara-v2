-- Six supported USDT networks: BEP20, TRC20, ARB, ETH, SOL, POLYGON.
-- TON remains in historical enum/migration history but is disabled operationally.
-- Network fees are authoritative configuration and are snapshotted per order.

alter type network_code add value if not exists 'POLYGON';

alter table network_configs
    add column if not exists network_fee_amount numeric(24,9) not null default 0;

alter table network_configs
    drop constraint if exists network_fee_nonnegative;

alter table network_configs
    add constraint network_fee_nonnegative
    check (service_fee_percent >= 0 and service_fee_percent < 100 and network_fee_amount >= 0);

insert into network_configs (
    code, display_name, enabled, address_regex, address_validator, requires_memo,
    explorer_url_template, service_fee_percent, network_fee_amount,
    min_amount, max_amount, icon_or_emoji, config_version
) values (
    'POLYGON', 'POLYGON', true, '^0x[0-9A-Fa-f]{40}$', 'evm_address', false,
    null, 0.000000, 0.200000000,
    0.001, 1000000, '🟣', 1
)
on conflict (code) do update set
    display_name = excluded.display_name,
    enabled = excluded.enabled,
    address_regex = excluded.address_regex,
    address_validator = excluded.address_validator,
    requires_memo = excluded.requires_memo,
    service_fee_percent = excluded.service_fee_percent,
    network_fee_amount = excluded.network_fee_amount,
    min_amount = excluded.min_amount,
    max_amount = excluded.max_amount,
    icon_or_emoji = excluded.icon_or_emoji,
    config_version = network_configs.config_version + 1,
    updated_at = now();

update network_configs
set enabled = case when code in ('BEP20','TRC20','ARB','ETH','SOL','POLYGON') then true else false end,
    network_fee_amount = case code
        when 'BEP20' then 0.150000000
        when 'TRC20' then 1.500000000
        when 'ARB' then 0.150000000
        when 'ETH' then 0.800000000
        when 'SOL' then 1.000000000
        when 'POLYGON' then 0.200000000
        else network_fee_amount
    end,
    config_version = config_version + 1,
    updated_at = now()
where code in ('BEP20','TRC20','TON','ARB','ETH','SOL','POLYGON');

alter table order_financial_snapshots
    add column if not exists network_fee_amount numeric(24,9) not null default 0;

alter table order_financial_snapshots
    drop constraint if exists financial_amounts_valid,
    drop constraint if exists financial_net_formula;

alter table order_financial_snapshots
    add constraint financial_amounts_valid
    check (fee_amount >= 0 and network_fee_amount >= 0 and net_usdt_amount > 0),
    add constraint financial_net_formula
    check (net_usdt_amount = round(requested_amount - fee_amount - network_fee_amount, 9));

create or replace function get_network_config_v2(
    p_code text
)
returns table (
    code network_code,
    display_name text,
    enabled boolean,
    address_regex text,
    requires_memo boolean,
    min_amount numeric,
    max_amount numeric,
    network_fee_amount numeric,
    config_version bigint
)
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_code is null or length(btrim(p_code)) = 0 then
        raise exception 'network code is required';
    end if;

    return query
    select
        nc.code,
        nc.display_name,
        nc.enabled,
        nc.address_regex,
        nc.requires_memo,
        nc.min_amount,
        nc.max_amount,
        nc.network_fee_amount,
        nc.config_version
    from network_configs nc
    where nc.code = upper(btrim(p_code))::network_code;
end;
$$;

revoke execute on function get_network_config_v2(text) from public, anon, authenticated;
grant execute on function get_network_config_v2(text) to service_role;

-- Replace the old order-creation RPC rather than keeping an insecure overload
-- that could omit the fixed network fee.
drop function if exists create_purchase_order_atomic(
    uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric,
    text, numeric, numeric, text, text, text, text, text, text, timestamptz,
    timestamptz, text, text
);

create function create_purchase_order_atomic(
    p_internal_order_id uuid,
    p_public_order_code text,
    p_user_id bigint,
    p_wallet_id uuid,
    p_network_code text,
    p_wallet_address text,
    p_requested_amount numeric,
    p_fee_percent numeric,
    p_fee_amount numeric,
    p_network_fee_amount numeric,
    p_net_usdt_amount numeric,
    p_payment_currency text,
    p_exchange_rate numeric,
    p_local_amount numeric,
    p_rounding_policy_version text,
    p_customer_verified_name_snapshot text,
    p_customer_shamcash_account_snapshot text,
    p_admin_payment_account_name_snapshot text,
    p_admin_payment_account_number_snapshot text,
    p_admin_payment_qr_file_id_snapshot text,
    p_quote_issued_at timestamptz,
    p_quote_expires_at timestamptz,
    p_idempotency_key text,
    p_operation text default 'create_purchase_order'
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_user_id uuid;
    v_wallet_user_id uuid;
    v_wallet_network network_code;
    v_wallet_status wallet_status;
    v_wallet_address text;
    v_network_enabled boolean;
    v_network_fee_amount numeric;
    v_service_fee_percent numeric;
    v_network_config_version bigint;
    v_min_amount numeric;
    v_max_amount numeric;
    v_identity_name text;
    v_identity_account text;
    v_identity_verified_at timestamptz;
    v_payment_method_id uuid;
    v_admin_name text;
    v_admin_number text;
    v_admin_qr text;
    v_status order_status;
    v_version bigint;
begin
    if p_internal_order_id is null then raise exception 'internal order id is required'; end if;
    if p_public_order_code is null or length(btrim(p_public_order_code)) < 4 then raise exception 'public order code is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_quote_issued_at is null or p_quote_expires_at is null or p_quote_expires_at <= p_quote_issued_at then raise exception 'invalid quote window'; end if;
    if p_quote_expires_at <= now() then raise exception 'quote has expired'; end if;
    if p_payment_currency not in ('USD', 'NEW.SYP') then raise exception 'unsupported payment currency'; end if;
    if p_requested_amount <= 0 then raise exception 'requested amount must be positive'; end if;
    if p_network_fee_amount < 0 then raise exception 'network fee must be non-negative'; end if;

    select ik.response_json
      into v_existing
      from idempotency_keys ik
     where ik.telegram_user_id = p_user_id
       and ik.operation = p_operation
       and ik.idempotency_key = p_idempotency_key
     for update;

    if found then
        return query
        select
            (v_existing ->> 'internal_order_id')::uuid,
            v_existing ->> 'public_order_code',
            (v_existing ->> 'status')::order_status,
            (v_existing ->> 'version')::bigint,
            true;
        return;
    end if;

    select u.id into v_user_id
      from users u
     where u.telegram_user_id = p_user_id
       and not u.is_disabled;
    if not found then raise exception 'customer not found or disabled'; end if;

    select w.user_id, w.network_code, w.status, w.address
      into v_wallet_user_id, v_wallet_network, v_wallet_status, v_wallet_address
      from wallets w
     where w.id = p_wallet_id
     for share;
    if not found then raise exception 'wallet not found'; end if;
    if v_wallet_user_id <> v_user_id then raise exception 'wallet does not belong to customer'; end if;
    if v_wallet_status <> 'VERIFIED' then raise exception 'wallet is not verified'; end if;
    if v_wallet_network <> p_network_code::network_code then raise exception 'wallet network mismatch'; end if;
    if btrim(v_wallet_address) <> btrim(p_wallet_address) then raise exception 'wallet address mismatch'; end if;

    select nc.enabled, nc.min_amount, nc.max_amount,
           nc.service_fee_percent, nc.network_fee_amount, nc.config_version
      into v_network_enabled, v_min_amount, v_max_amount,
           v_service_fee_percent, v_network_fee_amount, v_network_config_version
      from network_configs nc
     where nc.code = p_network_code::network_code
     for share;
    if not found or not v_network_enabled then raise exception 'network is unavailable'; end if;
    if p_requested_amount < v_min_amount or p_requested_amount > v_max_amount then raise exception 'amount is outside network limits'; end if;
    if p_fee_percent <> v_service_fee_percent then raise exception 'fee policy changed; refresh quote'; end if;
    if p_network_fee_amount <> v_network_fee_amount then raise exception 'network fee changed; refresh quote'; end if;
    if p_fee_amount <> round(p_requested_amount * p_fee_percent / 100, 9) then raise exception 'fee amount mismatch'; end if;
    if p_net_usdt_amount <> round(p_requested_amount - p_fee_amount - p_network_fee_amount, 9) then raise exception 'net amount mismatch'; end if;
    if p_net_usdt_amount <= 0 then raise exception 'net amount must remain positive'; end if;
    if p_payment_currency = 'USD' and p_exchange_rate is not null then raise exception 'USD payment must not include exchange rate'; end if;
    if p_payment_currency = 'NEW.SYP' and (p_exchange_rate is null or p_exchange_rate <= 0) then raise exception 'NEW.SYP payment requires exchange rate'; end if;
    if p_payment_currency = 'USD' and p_local_amount <> round(p_requested_amount, 9) then raise exception 'USD local amount mismatch'; end if;
    if p_payment_currency = 'NEW.SYP' and p_local_amount <> round(p_requested_amount * p_exchange_rate, 9) then raise exception 'NEW.SYP local amount mismatch'; end if;

    select u.verified_name, u.verified_shamcash_account, u.payment_identity_verified_at
      into v_identity_name, v_identity_account, v_identity_verified_at
      from users u
     where u.id = v_user_id
     for share;
    if v_identity_name is null or v_identity_account is null or v_identity_verified_at is null then
        raise exception 'customer payment identity is not verified';
    end if;
    if btrim(v_identity_name) <> btrim(p_customer_verified_name_snapshot)
       or btrim(v_identity_account) <> btrim(p_customer_shamcash_account_snapshot) then
        raise exception 'customer identity snapshot mismatch';
    end if;

    select pm.id into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH'
       and pm.status = 'ENABLED';
    if not found then raise exception 'ShamCash payment method is unavailable'; end if;

    select apa.account_name, apa.account_number, apa.qr_image_file_id
      into v_admin_name, v_admin_number, v_admin_qr
      from admin_payment_accounts apa
     where apa.payment_method_id = v_payment_method_id
       and apa.currency = p_payment_currency::currency_code
       and apa.is_active
     for share;
    if not found then raise exception 'admin payment account is unavailable'; end if;

    if btrim(v_admin_name) <> btrim(p_admin_payment_account_name_snapshot)
       or btrim(v_admin_number) <> btrim(p_admin_payment_account_number_snapshot)
       or coalesce(btrim(v_admin_qr), '') <> coalesce(btrim(p_admin_payment_qr_file_id_snapshot), '') then
        raise exception 'admin payment account snapshot mismatch';
    end if;

    insert into orders (
        internal_order_id, public_order_code, user_id, wallet_id, network_code,
        payment_method_id, status, version, expires_at
    ) values (
        p_internal_order_id, btrim(p_public_order_code), v_user_id, p_wallet_id,
        p_network_code::network_code, v_payment_method_id, 'PENDING_PAYMENT', 1, p_quote_expires_at
    ) returning orders.status, orders.version into v_status, v_version;

    insert into order_financial_snapshots (
        internal_order_id, requested_amount, fee_percent, fee_amount, network_fee_amount, net_usdt_amount,
        payment_currency, exchange_rate, local_amount, rounding_policy_version,
        network_config_version
    ) values (
        p_internal_order_id, p_requested_amount, p_fee_percent, p_fee_amount, p_network_fee_amount, p_net_usdt_amount,
        p_payment_currency::currency_code, p_exchange_rate, p_local_amount,
        p_rounding_policy_version, v_network_config_version
    );

    insert into audit_logs (
        actor_telegram_user_id, action, target_type, target_id, new_value, metadata
    ) values (
        p_user_id, 'order.created', 'order', p_internal_order_id::text,
        jsonb_build_object('public_order_code', p_public_order_code, 'status', v_status, 'version', v_version),
        jsonb_build_object('operation', p_operation, 'network_fee_amount', p_network_fee_amount)
    );

    insert into idempotency_keys (telegram_user_id, operation, idempotency_key, response_json)
    values (
        p_user_id, p_operation, p_idempotency_key,
        jsonb_build_object(
            'internal_order_id', p_internal_order_id,
            'public_order_code', p_public_order_code,
            'status', v_status,
            'version', v_version
        )
    );

    return query
    select p_internal_order_id, p_public_order_code, v_status, v_version, false;
exception
    when unique_violation then
        if exists (select 1 from orders o where o.public_order_code = p_public_order_code) then
            raise exception 'public order code collision';
        end if;
        if exists (select 1 from idempotency_keys ik where ik.telegram_user_id = p_user_id and ik.operation = p_operation and ik.idempotency_key = p_idempotency_key) then
            raise exception 'idempotency key collision';
        end if;
        raise;
end;
$$;

revoke execute on function create_purchase_order_atomic(
    uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, numeric,
    text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text
) from public, anon, authenticated;
grant execute on function create_purchase_order_atomic(
    uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, numeric,
    text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text
) to service_role;
