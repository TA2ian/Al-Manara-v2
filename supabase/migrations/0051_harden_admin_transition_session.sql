-- Administrative order review must be bound to the same recent session
-- at the database transition boundary. Application-side validation alone
-- is insufficient because it creates a TOCTOU window.

create or replace function transition_order_idempotent(
    p_order_id uuid,
    p_target_status order_status,
    p_expected_version bigint,
    p_actor_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_event_payload jsonb default '{}'::jsonb,
    p_session_id uuid default null
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    state_before order_status,
    state_after order_status,
    transitioned_at timestamptz,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_current_status order_status;
    v_current_version bigint;
    v_new_version bigint;
    v_actor_type admin_actor_type;
    v_existing jsonb;
begin
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_actor_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_session_id is null then raise exception 'admin session is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key is required';
    end if;

    -- Authorize before idempotency replay. This prevents disabled/revoked
    -- administrators from learning privileged replay results.
    select au.actor_type into v_actor_type
      from admin_users au
     where au.telegram_user_id = p_actor_telegram_user_id
       and au.enabled
       and au.actor_type = p_actor_type
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;

    if not exists (
        select 1 from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_actor_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    select ik.response_json into v_existing
      from idempotency_keys ik
     where ik.telegram_user_id = p_actor_telegram_user_id
       and ik.operation = 'admin_order_review'
       and ik.idempotency_key = btrim(p_idempotency_key)
     for update;
    if found then
        return query select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'state_before')::order_status,
            (v_existing->>'state_after')::order_status,
            (v_existing->>'transitioned_at')::timestamptz,
            true;
        return;
    end if;

    select o.status, o.version into v_current_status, v_current_version
      from orders o where o.internal_order_id = p_order_id for update;
    if not found then raise exception 'order not found'; end if;
    if v_current_version <> p_expected_version then
        raise exception using errcode='P0001', message='stale order version', detail=format('expected=%s current=%s', p_expected_version, v_current_version);
    end if;

    if not (
        (v_current_status = 'UNDER_REVIEW' and p_target_status in ('APPROVED', 'REJECTED', 'CLARIFICATION_REQUIRED'))
    ) then
        raise exception 'invalid administrative review transition';
    end if;

    v_new_version := v_current_version + 1;
    update orders o
       set status = p_target_status,
           version = v_new_version,
           approved_at = case when p_target_status = 'APPROVED' then coalesce(o.approved_at, now()) else o.approved_at end,
           rejection_reason = case when p_target_status = 'REJECTED' then nullif(btrim(coalesce(p_event_payload->>'reason','')), '') else o.rejection_reason end,
           clarification_reason = case when p_target_status = 'CLARIFICATION_REQUIRED' then nullif(btrim(coalesce(p_event_payload->>'reason','')), '') else o.clarification_reason end,
           updated_at = now()
     where o.internal_order_id = p_order_id
       and o.version = p_expected_version;
    if not found then raise exception 'order changed during transition'; end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_actor_telegram_user_id, v_actor_type, 'order.admin_reviewed', 'order', p_order_id::text,
        jsonb_build_object('status', v_current_status, 'version', p_expected_version),
        jsonb_build_object('status', p_target_status, 'version', v_new_version),
        coalesce(p_event_payload, '{}'::jsonb) || jsonb_build_object('session_id', p_session_id)
    );

    insert into idempotency_keys (telegram_user_id, operation, idempotency_key, response_json)
    values (
        p_actor_telegram_user_id, 'admin_order_review', btrim(p_idempotency_key),
        jsonb_build_object(
            'internal_order_id', p_order_id,
            'public_order_code', (select o.public_order_code from orders o where o.internal_order_id = p_order_id),
            'status', p_target_status,
            'version', v_new_version,
            'state_before', v_current_status,
            'state_after', p_target_status,
            'transitioned_at', now()
        )
    );

    return query select o.internal_order_id, o.public_order_code, o.status, o.version,
                         v_current_status, o.status, now(), false
      from orders o where o.internal_order_id = p_order_id;
end;
$$;

revoke all on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, text, jsonb, uuid) from public;
grant execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, text, jsonb, uuid) to service_role;
