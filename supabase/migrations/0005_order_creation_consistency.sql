create or replace function create_purchase_order_atomic(
    p_internal_order_id uuid,
    p_public_order_code text,
    p_user_id bigint,
    p_wallet_id uuid,
    p_network_code text,
    p_wallet_address text,
    p_requested_amount numeric,
    p_fee_percent numeric,
    p_fee_amount numeric,
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
returns table (internal_order_id uuid, public_order_code text, status text, version bigint, replayed boolean)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_status text;
    v_version bigint;
    v_wallet_user_id bigint;
    v_wallet_network text;
    v_wallet_address text;
    v_wallet_status text;
    v_network_enabled boolean;
    v_min_amount numeric;
    v_max_amount numeric;
    v_identity_name text;
    v_identity_account text;
begin
    if length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_quote_issued_at is null or p_quote_expires_at is null or p_quote_expires_at <= p_quote_issued_at then raise exception 'invalid quote window'; end if;
    if p_public_order_code is null or length(btrim(p_public_order_code)) = 0 then raise exception 'public order code is required'; end if;

    select response_json into v_existing
      from idempotency_keys
     where user_id = p_user_id and idempotency_key = p_idempotency_key and operation = p_operation
     for update;
    if found then
        return query select (v_existing->>'internal_order_id')::uuid, v_existing->>'public_order_code', v_existing->>'status', (v_existing->>'version')::bigint, true;
        return;
    end if;

    select w.user_id, w.network_code, w.address, w.status
      into v_wallet_user_id, v_wallet_network, v_wallet_address, v_wallet_status
      from wallets w where w.wallet_id = p_wallet_id for share;
    if not found then raise exception 'wallet not found'; end if;
    if v_wallet_user_id <> p_user_id then raise exception 'wallet does not belong to customer'; end if;
    if v_wallet_status <> 'verified' then raise exception 'wallet is not verified'; end if;
    if v_wallet_network <> p_network_code then raise exception 'wallet network mismatch'; end if;
    if lower(btrim(v_wallet_address)) <> lower(btrim(p_wallet_address)) then raise exception 'wallet address mismatch'; end if;

    select n.enabled, n.min_amount, n.max_amount into v_network_enabled, v_min_amount, v_max_amount
      from network_configs n where n.code = p_network_code for share;
    if not found or not v_network_enabled then raise exception 'network is unavailable'; end if;
    if p_requested_amount < v_min_amount or p_requested_amount > v_max_amount then raise exception 'amount is outside network limits'; end if;

    select c.verified_name, c.verified_shamcash_account into v_identity_name, v_identity_account
      from customer_payment_identities c where c.user_id = p_user_id for share;
    if not found then raise exception 'customer payment identity is not verified'; end if;
    if btrim(v_identity_name) <> btrim(p_customer_verified_name_snapshot) or btrim(v_identity_account) <> btrim(p_customer_shamcash_account_snapshot) then
        raise exception 'customer identity snapshot mismatch';
    end if;

    insert into orders (
        internal_order_id, public_order_code, user_id, wallet_id, network_code, wallet_address,
        status, version, requested_amount, fee_percent, fee_amount, net_usdt_amount,
        payment_currency, exchange_rate, local_amount, rounding_policy_version,
        customer_verified_name_snapshot, customer_shamcash_account_snapshot,
        admin_payment_account_name_snapshot, admin_payment_account_number_snapshot,
        admin_payment_qr_file_id_snapshot, quote_issued_at, quote_expires_at
    ) values (
        p_internal_order_id, p_public_order_code, p_user_id, p_wallet_id, p_network_code, btrim(v_wallet_address),
        'draft', 0, p_requested_amount, p_fee_percent, p_fee_amount, p_net_usdt_amount,
        p_payment_currency, p_exchange_rate, p_local_amount, p_rounding_policy_version,
        btrim(v_identity_name), btrim(v_identity_account), btrim(p_admin_payment_account_name_snapshot),
        btrim(p_admin_payment_account_number_snapshot), btrim(p_admin_payment_qr_file_id_snapshot),
        p_quote_issued_at, p_quote_expires_at
    ) returning orders.status, orders.version into v_status, v_version;

    insert into audit_events (order_id, actor_type, actor_id, event_type, event_payload)
    values (p_internal_order_id, 'customer', p_user_id::text, 'order.created',
            jsonb_build_object('public_order_code', p_public_order_code, 'version', v_version));

    insert into idempotency_keys (user_id, idempotency_key, operation, response_json)
    values (p_user_id, p_idempotency_key, p_operation,
            jsonb_build_object('internal_order_id', p_internal_order_id, 'public_order_code', p_public_order_code, 'status', v_status, 'version', v_version));

    return query select p_internal_order_id, p_public_order_code, v_status, v_version, false;
exception when unique_violation then
    if exists (select 1 from orders where public_order_code = p_public_order_code) then raise exception 'public order code collision'; end if;
    if exists (select 1 from idempotency_keys where user_id = p_user_id and idempotency_key = p_idempotency_key and operation = p_operation) then
        raise exception 'idempotency key collision';
    end if;
    raise;
end;
$$;
