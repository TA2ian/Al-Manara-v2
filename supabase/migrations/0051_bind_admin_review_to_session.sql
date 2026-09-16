-- Sensitive admin order review must be authorized by the same recent
-- session that reaches the authoritative transition. Session validation is
-- intentionally performed before idempotency replay to prevent revoked or
-- expired sessions from replaying privileged results.

create or replace function transition_order_idempotent(
    p_order_id uuid,
    p_target_status order_status,
    p_expected_version bigint,
    p_actor_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_event_payload jsonb default '{}'::jsonb,
    p_idempotency_key text default null,
    p_session_id uuid default null
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    state_before order_status,
    transitioned_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_current_status order_status;
    v_current_version bigint;
    v_new_version bigint;
    v_public_order_code text;
    v_transitioned_at timestamptz;
    v_registered_actor_type admin_actor_type;
begin
    if p_expected_version <= 0 then
        raise exception 'expected version must be positive';
    end if;
    if p_actor_telegram_user_id <= 0 then
        raise exception 'actor id must be positive';
    end if;
    if p_actor_type is null then
        raise exception 'actor type is required';
    end if;
    if p_session_id is null then
        raise exception 'admin session is required';
    end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key is required';
    end if;

    -- Resolve and authorize the actor from the authoritative admin record.
    select au.actor_type
      into v_registered_actor_type
      from admin_users au
     where au.telegram_user_id = p_actor_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;

    if not found then
        raise exception 'admin is not enabled';
    end if;
    if v_registered_actor_type <> p_actor_type then
        raise exception 'admin actor type mismatch';
    end if;

    -- The session is bound to both the Telegram identity and its authoritative
    -- actor type. Validate it before idempotency replay.
    if not exists (
        select 1
          from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_actor_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    select oti.result
      into v_existing
      from order_transition_idempotency oti
     where oti.idempotency_key = btrim(p_idempotency_key)
     for update;

    if found then
        if coalesce((v_existing->>'finalized')::boolean, true) then
            if (v_existing->>'internal_order_id')::uuid <> p_order_id
               or (v_existing->>'target_status')::order_status <> p_target_status
               or (v_existing->>'expected_version')::bigint <> p_expected_version
               or (v_existing->>'actor_telegram_user_id')::bigint <> p_actor_telegram_user_id
               or (v_existing->>'actor_type')::admin_actor_type <> p_actor_type then
                raise exception 'idempotency key belongs to another transition';
            end if;
            return query
            select
                (v_existing->>'internal_order_id')::uuid,
                v_existing->>'public_order_code',
                (v_existing->>'status')::order_status,
                (v_existing->>'version')::bigint,
                (v_existing->>'state_before')::order_status,
                (v_existing->>'transitioned_at')::timestamptz;
            return;
        end if;
    end if;

    -- A non-finalized row is a reservation made by this same RPC. The order
    -- lock and transition remain in the same PostgreSQL transaction.
    if not found then
        insert into order_transition_idempotency (
            idempotency_key, internal_order_id, target_status, expected_version,
            actor_telegram_user_id, actor_type, result
        ) values (
            btrim(p_idempotency_key), p_order_id, p_target_status, p_expected_version,
            p_actor_telegram_user_id, p_actor_type,
            jsonb_build_object('finalized', false)
        );
    end if;

    select oti.result
      into v_existing
      from order_transition_idempotency oti
     where oti.idempotency_key = btrim(p_idempotency_key)
     for update;

    if not found then
        raise exception 'idempotency reservation disappeared';
    end if;

    if coalesce((v_existing->>'finalized')::boolean, true) then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'target_status')::order_status <> p_target_status
           or (v_existing->>'expected_version')::bigint <> p_expected_version
           or (v_existing->>'actor_telegram_user_id')::bigint <> p_actor_telegram_user_id
           or (v_existing->>'actor_type')::admin_actor_type <> p_actor_type then
            raise exception 'idempotency key belongs to another transition';
        end if;
        return query
        select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'state_before')::order_status,
            (v_existing->>'transitioned_at')::timestamptz;
        return;
    end if;

    select o.status, o.version, o.public_order_code
      into v_current_status, v_current_version, v_public_order_code
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
    if not (v_current_status = 'UNDER_REVIEW' and p_target_status in ('APPROVED', 'REJECTED', 'CLARIFICATION_REQUIRED')) then
        raise exception 'invalid idempotent admin review transition: % -> %', v_current_status, p_target_status;
    end if;

    v_new_version := v_current_version + 1;
    v_transitioned_at := now();

    update orders
       set status = p_target_status,
           version = v_new_version,
           approved_at = case when p_target_status = 'APPROVED' then coalesce(approved_at, v_transitioned_at) else approved_at end,
           updated_at = v_transitioned_at
     where internal_order_id = p_order_id
       and version = p_expected_version;

    if not found then
        raise exception 'order changed during transition';
    end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_actor_telegram_user_id, p_actor_type, 'order.status_changed', 'order', p_order_id::text,
        jsonb_build_object('status', v_current_status, 'version', p_expected_version),
        jsonb_build_object('status', p_target_status, 'version', v_new_version),
        coalesce(p_event_payload, '{}'::jsonb) || jsonb_build_object(
            'public_order_code', v_public_order_code,
            'session_id', p_session_id
        )
    );

    update order_transition_idempotency
       set result = jsonb_build_object(
           'finalized', true,
           'internal_order_id', p_order_id,
           'public_order_code', v_public_order_code,
           'status', p_target_status,
           'version', v_new_version,
           'state_before', v_current_status,
           'target_status', p_target_status,
           'expected_version', p_expected_version,
           'actor_telegram_user_id', p_actor_telegram_user_id,
           'actor_type', p_actor_type,
           'transitioned_at', v_transitioned_at
       )
     where idempotency_key = btrim(p_idempotency_key);

    return query select p_order_id, v_public_order_code, p_target_status, v_new_version,
        v_current_status, v_transitioned_at;
end;
$$;

revoke execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text, uuid) from public;
grant execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text, uuid) to service_role;
