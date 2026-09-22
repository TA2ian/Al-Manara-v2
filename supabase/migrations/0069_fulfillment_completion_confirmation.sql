-- Require a one-time shared admin confirmation after the manual TXID is entered.
-- The confirmation is bound by the application to the exact order/version/admin/TXID
-- request fingerprint and is atomically consumed before the first completion mutation.
-- Completion is a manual operational confirmation for every enabled USDT network.
-- The RPC never submits a blockchain transaction; it only records the TXID/hash
-- after the administrator has completed the transfer.

-- Extend the existing shared confirmation contract without rewriting migration 0067.
alter table admin_action_confirmations
    drop constraint if exists admin_action_confirmation_operation;

alter table admin_action_confirmations
    add constraint admin_action_confirmation_operation check (
        operation in (
            'admin_payment_account.upsert',
            'admin_payment_account.status',
            'fulfillment.complete'
        )
    );

create or replace function create_admin_action_confirmation(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid,
    p_operation text,
    p_request_fingerprint text
)
returns table (confirmation_id uuid, expires_at timestamptz)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_confirmation_id uuid;
    v_expires timestamptz;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0 then
        raise exception 'admin identity is required';
    end if;
    if p_actor_type is null or p_session_id is null then
        raise exception 'admin session is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert', 'admin_payment_account.status', 'fulfillment.complete') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;

    if not validate_admin_session(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    v_expires := now() + interval '90 seconds';

    insert into admin_action_confirmations(
        admin_telegram_user_id,
        actor_type,
        session_id,
        operation,
        request_fingerprint,
        expires_at
    )
    values (
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_operation,
        p_request_fingerprint,
        v_expires
    )
    returning id, admin_action_confirmations.expires_at
      into v_confirmation_id, v_expires;

    insert into audit_logs(
        actor_telegram_user_id,
        actor_kind,
        actor_type,
        action,
        target_type,
        target_id,
        confirmation_id,
        metadata
    )
    values (
        p_admin_telegram_user_id,
        'admin',
        p_actor_type,
        'admin.action_confirmation.created',
        'admin_action_confirmation',
        v_confirmation_id::text,
        v_confirmation_id,
        jsonb_build_object(
            'operation', p_operation,
            'expires_at', v_expires
        )
    );

    return query select v_confirmation_id, v_expires;
end;
$$;


create or replace function consume_admin_action_confirmation(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid,
    p_confirmation_id uuid,
    p_operation text,
    p_request_fingerprint text
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_changed boolean;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0 then
        raise exception 'admin identity is required';
    end if;
    if p_actor_type is null or p_session_id is null or p_confirmation_id is null then
        raise exception 'admin confirmation is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert', 'admin_payment_account.status', 'fulfillment.complete') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;

    if not validate_admin_session(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    update admin_action_confirmations
       set consumed_at = now()
     where id = p_confirmation_id
       and admin_telegram_user_id = p_admin_telegram_user_id
       and actor_type = p_actor_type
       and session_id = p_session_id
       and operation = p_operation
       and request_fingerprint = p_request_fingerprint
       and consumed_at is null
       and expires_at > now();

    v_changed := found;

    if not v_changed then
        raise exception 'admin action confirmation is invalid, expired, or already consumed';
    end if;

    return true;
end;
$$;


drop function if exists public.complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, uuid, text);

create or replace function public.complete_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_session_id uuid,
    p_transfer_reference text,
    p_confirmation_id uuid,
    p_request_fingerprint text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    completed_at timestamptz,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_status order_status;
    v_version bigint;
    v_actor_type admin_actor_type;
    v_claim_admin bigint;
    v_completed_at timestamptz;
    v_order_code text;
    v_network network_code;
    v_net_usdt numeric(24,9);
    v_reference text := btrim(coalesce(p_transfer_reference, ''));
    v_result jsonb;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_session_id is null then raise exception 'admin session is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
    end if;
    if length(v_reference) <> 64 or v_reference !~ '^[0-9A-Fa-f]{64}$' then
        raise exception 'transfer reference must be a 64-character hexadecimal transaction hash';
    end if;
    if p_confirmation_id is null then
        raise exception 'fulfillment confirmation is required';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid fulfillment confirmation fingerprint';
    end if;

    select au.actor_type into v_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;
    if v_actor_type <> p_actor_type then raise exception 'admin actor type mismatch'; end if;

    if not exists (
        select 1 from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_admin_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    select f.result into v_existing
      from order_fulfillment_idempotency f
     where f.idempotency_key = btrim(p_idempotency_key)
       and f.operation = 'complete'
     for update;
    if found then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'admin_telegram_user_id')::bigint <> p_admin_telegram_user_id
           or coalesce(v_existing->>'transfer_reference','') <> v_reference
        then
            raise exception 'idempotency key belongs to another fulfillment operation';
        end if;
        return query select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'completed_at')::timestamptz,
            true;
        return;
    end if;

    perform consume_admin_action_confirmation(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_confirmation_id,
        'fulfillment.complete',
        p_request_fingerprint
    );

    select o.status, o.version, o.public_order_code, o.network_code
      into v_status, v_version, v_order_code, v_network
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_version <> p_expected_version then
        raise exception using errcode='P0001', message='stale order version', detail=format('expected=%s current=%s', p_expected_version, v_version);
    end if;
    if v_status <> 'APPROVED' then raise exception 'order is not eligible for fulfillment completion'; end if;

    if v_network not in ('BEP20','TRC20','ARB','ETH','SOL','POLYGON') then
        raise exception 'network is not enabled for manual USDT fulfillment';
    end if;

    select fs.net_usdt_amount into v_net_usdt
      from order_financial_snapshots fs
     where fs.internal_order_id = p_order_id;
    if v_net_usdt is null or v_net_usdt <= 0 then
        raise exception 'order has no valid net USDT fulfillment amount';
    end if;

    if exists (
        select 1
          from orders o
         where o.manual_usdt_transfer_reference = v_reference
           and o.internal_order_id <> p_order_id
    ) then
        raise exception 'transfer reference is already recorded on another order';
    end if;

    select fc.admin_telegram_user_id into v_claim_admin
      from order_fulfillment_claims fc
     where fc.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'active fulfillment claim is required'; end if;
    if v_claim_admin <> p_admin_telegram_user_id then raise exception 'fulfillment claim belongs to another admin'; end if;

    v_completed_at := now();

    update orders as ord
       set status = 'COMPLETED',
           version = ord.version + 1,
           manual_usdt_transfer_reference = v_reference,
           completed_at = v_completed_at,
           updated_at = now()
     where ord.internal_order_id = p_order_id
       and ord.version = p_expected_version;
    if not found then raise exception 'order changed concurrently'; end if;

    delete from order_fulfillment_claims as fc where fc.internal_order_id = p_order_id;

    insert into audit_logs (
        actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id,
        confirmation_id, old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, 'admin', v_actor_type, 'order.fulfillment_completed', 'order', p_order_id::text,
        p_confirmation_id, jsonb_build_object('status', v_status, 'version', p_expected_version),
        jsonb_build_object(
            'status', 'COMPLETED',
            'version', p_expected_version + 1,
            'manual_usdt_transfer_reference', v_reference
        ),
        jsonb_build_object(
            'operation', 'fulfillment_completion',
            'claim_admin_telegram_user_id', v_claim_admin,
            'network_code', v_network,
            'net_usdt_amount', v_net_usdt,
            'session_id', p_session_id
        )
    );

    v_result := jsonb_build_object(
        'internal_order_id', p_order_id,
        'public_order_code', v_order_code,
        'status', 'COMPLETED',
        'version', p_expected_version + 1,
        'completed_at', v_completed_at,
        'admin_telegram_user_id', p_admin_telegram_user_id,
        'transfer_reference', v_reference
    );
    insert into order_fulfillment_idempotency (
        idempotency_key, operation, internal_order_id, admin_telegram_user_id,
        expected_version, result
    ) values (
        btrim(p_idempotency_key), 'complete', p_order_id, p_admin_telegram_user_id,
        p_expected_version, v_result
    );

    return query select
        p_order_id, v_order_code, 'COMPLETED'::order_status,
        p_expected_version + 1, v_completed_at, false;
end;
$$;

revoke all on function public.complete_order_fulfillment(
    uuid, bigint, bigint, admin_actor_type, text, uuid, text, uuid, text
) from public, anon, authenticated;

grant execute on function public.complete_order_fulfillment(
    uuid, bigint, bigint, admin_actor_type, text, uuid, text, uuid, text
) to service_role;
