-- Dedicated Admin Order Review transition boundary.
-- Keeps the generic order transition RPC independent from admin session policy.

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
    v_session admin_sessions%rowtype;
    v_before order_status;
begin
    if p_order_id is null or p_expected_version < 1 or p_admin_telegram_user_id < 1
       or p_actor_type is null or p_session_id is null
       or length(btrim(coalesce(p_idempotency_key, ''))) = 0
       or length(btrim(p_idempotency_key)) > 200 then
        raise exception 'invalid admin transition input';
    end if;

    select * into v_admin
      from admin_users
     where telegram_user_id = p_admin_telegram_user_id
       and enabled = true
       and actor_type = p_actor_type
       and (actor_type = 'primary' or emergency_only = true);
    if not found then
        raise exception 'admin authorization failed';
    end if;

    select * into v_session
      from admin_sessions
     where id = p_session_id
       and admin_telegram_user_id = p_admin_telegram_user_id
       and actor_type = p_actor_type
       and revoked_at is null
       and expires_at > now();
    if not found then
        raise exception 'admin session invalid';
    end if;

    -- Authorization deliberately precedes replay so a stolen idempotency key
    -- cannot become an authorization oracle.
    return query
    select o.internal_order_id, o.public_order_code, o.status, o.version,
           o.status, o.status, o.updated_at
      from orders o
     where false;

    select * into v_order
      from orders
     where internal_order_id = p_order_id
     for update;
    if not found then
        raise exception 'order not found';
    end if;

    if v_order.version <> p_expected_version then
        raise exception 'stale order version';
    end if;

    if v_order.status <> 'UNDER_REVIEW' or p_target_status not in ('APPROVED','REJECTED','CLARIFICATION_REQUIRED') then
        raise exception 'invalid admin review transition';
    end if;

    v_before := v_order.status;

    update orders
       set status = p_target_status,
           version = version + 1,
           rejection_reason = case when p_target_status = 'REJECTED' then nullif(btrim(p_event_payload->>'reason'),'') else rejection_reason end,
           clarification_reason = case when p_target_status = 'CLARIFICATION_REQUIRED' then nullif(btrim(p_event_payload->>'reason'),'') else clarification_reason end,
           approved_at = case when p_target_status = 'APPROVED' then now() else approved_at end,
           updated_at = now()
     where internal_order_id = p_order_id;

    insert into audit_logs (actor_telegram_user_id, actor_type, action, entity_type, entity_id, metadata)
    values (p_admin_telegram_user_id, p_actor_type, 'ADMIN_ORDER_REVIEW', 'order', p_order_id,
            coalesce(p_event_payload, '{}'::jsonb) || jsonb_build_object('session_id', p_session_id::text, 'state_before', v_before::text, 'state_after', p_target_status::text));

    return query
    select o.internal_order_id, o.public_order_code, o.status, o.version,
           v_before, o.status, o.updated_at
      from orders o
     where o.internal_order_id = p_order_id;
end;
$$;

revoke all on function admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid) from public;
grant execute on function admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid) to service_role;
