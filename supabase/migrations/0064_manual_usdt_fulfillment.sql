-- Final manual fulfillment hardening.
-- Completion requires a recorded blockchain transaction hash and only permits
-- operational networks explicitly supported for manual transfer: BEP20/TRC20.
-- Blockchain submission itself remains manual; this RPC only records the
-- administrator's confirmation after the transfer has been made.

drop function if exists public.complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, uuid);

create function public.complete_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_session_id uuid,
    p_transfer_reference text
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
    if v_network not in ('BEP20','TRC20') then
        raise exception 'manual USDT fulfillment is restricted to BEP20 or TRC20';
    end if;

    select fs.net_usdt_amount into v_net_usdt
      from order_financial_snapshots fs
     where fs.internal_order_id = p_order_id;
    if v_net_usdt is null or v_net_usdt <= 0 then
        raise exception 'order has no valid net USDT fulfillment amount';
    end if;

    select fc.admin_telegram_user_id into v_claim_admin
      from order_fulfillment_claims fc
     where fc.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'active fulfillment claim is required'; end if;
    if v_claim_admin <> p_admin_telegram_user_id then raise exception 'fulfillment claim belongs to another admin'; end if;

    v_completed_at := now();

    update orders
       set status = 'COMPLETED',
           version = version + 1,
           manual_usdt_transfer_reference = v_reference,
           completed_at = v_completed_at,
           updated_at = now()
     where internal_order_id = p_order_id
       and version = p_expected_version;
    if not found then raise exception 'order changed concurrently'; end if;

    delete from order_fulfillment_claims where internal_order_id = p_order_id;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'order.fulfillment_completed', 'order', p_order_id::text,
        jsonb_build_object('status', v_status, 'version', p_expected_version),
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

grant execute on function public.complete_order_fulfillment(
    uuid, bigint, bigint, admin_actor_type, text, uuid, text
) to service_role;
