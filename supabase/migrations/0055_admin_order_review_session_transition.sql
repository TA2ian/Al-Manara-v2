-- Dedicated Admin Order Review transition boundary.
-- Keeps the generic order transition RPC independent from admin session policy.
-- This boundary owns its own idempotent replay so the generic transition path
-- remains reusable for non-review transitions.

create or replace function admin_review_order_transition_idempotent(
    p_order_id uuid,
    p_target_status order_status,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_event_payload jsonb,
    p_session_id uuid
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    state_before order_status,
    state_after order_status,
    transitioned_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_order orders%rowtype;
    v_admin admin_users%rowtype;
    v_existing jsonb;
    v_reason text := btrim(coalesce(p_event_payload->>'reason', ''));
    v_before order_status;
    v_after order_status;
    v_transitioned_at timestamptz;
begin
    if p_order_id is null
       or p_expected_version < 1
       or p_admin_telegram_user_id < 1
       or p_actor_type is null
       or p_session_id is null
       or p_target_status not in ('APPROVED','REJECTED','CLARIFICATION_REQUIRED')
       or length(btrim(coalesce(p_idempotency_key, ''))) = 0
       or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'invalid admin review transition input';
    end if;

    if p_target_status in ('REJECTED','CLARIFICATION_REQUIRED')
       and (length(v_reason) < 5 or length(v_reason) > 1000) then
        raise exception 'review reason is required';
    end if;

    -- Resolve authorization from the authoritative admin record.
    select au.*
      into v_admin
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and au.actor_type = p_actor_type
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then
        raise exception 'admin authorization failed';
    end if;

    -- The explicit session is checked before replay so an old/revoked session
    -- cannot use a previously successful idempotency key as an authorization oracle.
    if not exists (
        select 1
          from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_admin_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session invalid or expired';
    end if;

    select ik.response_json
      into v_existing
      from idempotency_keys ik
     where ik.telegram_user_id = p_admin_telegram_user_id
       and ik.operation = 'admin_order_review_transition'
       and ik.idempotency_key = btrim(p_idempotency_key)
     for update;

    if found then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'state_after')::order_status <> p_target_status then
            raise exception 'idempotency key is bound to a different review operation';
        end if;

        return query
        select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'state_before')::order_status,
            (v_existing->>'state_after')::order_status,
            (v_existing->>'transitioned_at')::timestamptz;
        return;
    end if;

    -- Serialize the state transition and version check at the database boundary.
    select *
      into v_order
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then
        raise exception 'order not found';
    end if;

    if v_order.version <> p_expected_version then
        raise exception using
            errcode = 'P0001',
            message = 'stale order version',
            detail = format('expected=%s current=%s', p_expected_version, v_order.version);
    end if;

    if v_order.status <> 'UNDER_REVIEW' then
        raise exception 'order is not under review';
    end if;

    v_before := v_order.status;
    v_after := p_target_status;
    v_transitioned_at := now();

    update orders as o
       set status = p_target_status,
           version = o.version + 1,
           rejection_reason = case
               when p_target_status = 'REJECTED' then v_reason
               else o.rejection_reason
           end,
           clarification_reason = case
               when p_target_status = 'CLARIFICATION_REQUIRED' then v_reason
               else o.clarification_reason
           end,
           approved_at = case
               when p_target_status = 'APPROVED' then coalesce(o.approved_at, v_transitioned_at)
               else o.approved_at
           end,
           updated_at = v_transitioned_at
     where o.internal_order_id = p_order_id
       and o.version = p_expected_version;
    if not found then
        raise exception 'order changed concurrently';
    end if;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_type,
        action,
        target_type,
        target_id,
        old_value,
        new_value,
        metadata
    ) values (
        p_admin_telegram_user_id,
        p_actor_type,
        'order.admin_reviewed',
        'order',
        p_order_id::text,
        jsonb_build_object('status', v_before, 'version', p_expected_version),
        jsonb_build_object('status', p_target_status, 'version', p_expected_version + 1),
        coalesce(p_event_payload, '{}'::jsonb)
            || jsonb_build_object('session_id', p_session_id::text)
    );

    insert into idempotency_keys (
        telegram_user_id,
        operation,
        idempotency_key,
        response_json
    ) values (
        p_admin_telegram_user_id,
        'admin_order_review_transition',
        btrim(p_idempotency_key),
        jsonb_build_object(
            'internal_order_id', p_order_id,
            'public_order_code', v_order.public_order_code,
            'status', p_target_status,
            'version', p_expected_version + 1,
            'state_before', v_before,
            'state_after', v_after,
            'transitioned_at', v_transitioned_at
        )
    );

    return query
    select
        o.internal_order_id,
        o.public_order_code,
        o.status,
        o.version,
        v_before,
        o.status,
        v_transitioned_at
      from orders o
     where o.internal_order_id = p_order_id;
end;
$$;

revoke all on function admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid) from public;
grant execute on function admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid) to service_role;
