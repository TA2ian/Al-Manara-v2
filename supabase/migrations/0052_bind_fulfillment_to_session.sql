-- Fulfillment claim/completion are sensitive admin operations. Keep the
-- existing mutation implementation, but expose only session-bound overloads.
-- The old signatures are revoked from service_role so the application cannot
-- bypass the session boundary.

create or replace function claim_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_session_id uuid
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    admin_telegram_user_id bigint,
    claimed_at timestamptz,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_actor_type admin_actor_type;
    v_result record;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_session_id is null then raise exception 'admin session is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
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

    select * into v_result
      from claim_order_fulfillment(
          p_order_id,
          p_expected_version,
          p_admin_telegram_user_id,
          p_actor_type,
          btrim(p_idempotency_key)
      );

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'admin.session_authorized_fulfillment_claim', 'order', p_order_id::text,
        '{}'::jsonb,
        jsonb_build_object('session_id', p_session_id),
        jsonb_build_object('operation', 'fulfillment_claim')
    );

    return query select
        v_result.internal_order_id,
        v_result.public_order_code,
        v_result.status,
        v_result.version,
        v_result.admin_telegram_user_id,
        v_result.claimed_at,
        v_result.replayed;
end;
$$;

create or replace function complete_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_session_id uuid
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
    v_actor_type admin_actor_type;
    v_result record;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_session_id is null then raise exception 'admin session is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
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

    select * into v_result
      from complete_order_fulfillment(
          p_order_id,
          p_expected_version,
          p_admin_telegram_user_id,
          p_actor_type,
          btrim(p_idempotency_key)
      );

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'admin.session_authorized_fulfillment_completion', 'order', p_order_id::text,
        '{}'::jsonb,
        jsonb_build_object('session_id', p_session_id),
        jsonb_build_object('operation', 'fulfillment_completion')
    );

    return query select
        v_result.internal_order_id,
        v_result.public_order_code,
        v_result.status,
        v_result.version,
        v_result.completed_at,
        v_result.replayed;
end;
$$;

revoke execute on function claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) from public, service_role;
revoke execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) from public, service_role;
grant execute on function claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, uuid) to service_role;
grant execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, uuid) to service_role;
