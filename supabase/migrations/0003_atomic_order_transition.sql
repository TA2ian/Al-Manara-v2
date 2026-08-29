create or replace function transition_order_if_version(
    p_order_id uuid,
    p_target_status text,
    p_expected_version bigint,
    p_actor_type text,
    p_actor_id text,
    p_event_payload jsonb default '{}'::jsonb
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status text,
    version bigint
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_current_status text;
    v_current_version bigint;
    v_new_version bigint;
    v_transition_allowed boolean := false;
begin
    if p_expected_version < 0 then
        raise exception 'expected version must be non-negative';
    end if;

    if p_actor_type not in ('system', 'customer', 'admin') then
        raise exception 'invalid actor type';
    end if;

    select o.status, o.version
      into v_current_status, v_current_version
      from orders o
     where o.internal_order_id = p_order_id
     for update;

    if not found then
        raise exception 'order not found';
    end if;

    if v_current_version <> p_expected_version then
        raise exception using
            errcode = 'P0001',
            message = 'stale order version',
            detail = format('expected=%s current=%s', p_expected_version, v_current_version);
    end if;

    v_transition_allowed := case v_current_status
        when 'draft' then p_target_status in ('awaiting_payment', 'cancelled')
        when 'awaiting_payment' then p_target_status in ('receipt_submitted', 'expired', 'cancelled')
        when 'receipt_submitted' then p_target_status in ('under_review', 'expired')
        when 'under_review' then p_target_status in ('approved', 'rejected')
        when 'approved' then p_target_status in ('completed')
        else false
    end;

    if not v_transition_allowed then
        raise exception 'invalid order transition: % -> %', v_current_status, p_target_status;
    end if;

    v_new_version := v_current_version + 1;

    update orders
       set status = p_target_status,
           version = v_new_version,
           updated_at = now()
     where internal_order_id = p_order_id
       and version = p_expected_version;

    if not found then
        raise exception 'order changed during transition';
    end if;

    insert into audit_events (
        order_id,
        actor_type,
        actor_id,
        event_type,
        event_payload
    ) values (
        p_order_id,
        p_actor_type,
        p_actor_id,
        'order.status_changed',
        jsonb_build_object(
            'from_status', v_current_status,
            'to_status', p_target_status,
            'version_before', p_expected_version,
            'version_after', v_new_version
        ) || coalesce(p_event_payload, '{}'::jsonb)
    );

    return query
    select o.internal_order_id, o.public_order_code, o.status, o.version
      from orders o
     where o.internal_order_id = p_order_id;
end;
$$;
