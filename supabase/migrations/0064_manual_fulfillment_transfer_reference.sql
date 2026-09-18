-- Bind final fulfillment completion to the manual transfer record.
-- Completion is only valid after an administrator has performed the USDT transfer
-- and supplied its reference. Operational manual fulfillment is restricted to
-- BEP20/TRC20 as required by the business flow.

create or replace function complete_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_manual_usdt_transfer_reference text,
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
    v_reference text := btrim(coalesce(p_manual_usdt_transfer_reference, ''));
    v_network network_code;
    v_existing_reference text;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_session_id is null then raise exception 'admin session is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
    end if;
    if length(v_reference) < 1 or length(v_reference) > 200 then
        raise exception 'manual USDT transfer reference must be between 1 and 200 characters';
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

    select o.network_code, o.manual_usdt_transfer_reference
      into v_network, v_existing_reference
      from orders o
     where o.internal_order_id = p_order_id
     for share;
    if not found then raise exception 'order not found'; end if;

    if v_network not in ('BEP20', 'TRC20') then
        raise exception 'manual USDT fulfillment is restricted to BEP20 or TRC20';
    end if;

    -- Replay is safe only when the supplied reference is exactly the one
    -- already persisted for this completion. A different reference must never
    -- be accepted under the same idempotency key.
    if v_existing_reference is not null then
        if v_existing_reference <> v_reference then
            raise exception 'transfer reference does not match completed fulfillment';
        end if;
        select * into v_result
          from complete_order_fulfillment(
              p_order_id,
              p_expected_version,
              p_admin_telegram_user_id,
              p_actor_type,
              btrim(p_idempotency_key)
          );
        return query select
            v_result.internal_order_id,
            v_result.public_order_code,
            v_result.status,
            v_result.version,
            v_result.completed_at,
            v_result.replayed;
        return;
    end if;

    select * into v_result
      from complete_order_fulfillment(
          p_order_id,
          p_expected_version,
          p_admin_telegram_user_id,
          p_actor_type,
          btrim(p_idempotency_key)
      );

    update orders
       set manual_usdt_transfer_reference = v_reference,
           updated_at = now()
     where internal_order_id = p_order_id
       and status = 'COMPLETED'
       and version = v_result.version;

    if not found then
        raise exception 'completed order could not be bound to transfer reference';
    end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'order.fulfillment_transfer_recorded', 'order', p_order_id::text,
        jsonb_build_object('manual_usdt_transfer_reference', null),
        jsonb_build_object(
            'manual_usdt_transfer_reference', v_reference,
            'network_code', v_network,
            'version', v_result.version
        ),
        jsonb_build_object(
            'operation', 'fulfillment_transfer_record',
            'session_id', p_session_id,
            'idempotency_key', btrim(p_idempotency_key)
        )
    );

    return query select
        v_result.internal_order_id,
        v_result.public_order_code,
        v_result.status,
        v_result.version,
        v_result.completed_at,
        false;
end;
$$;

revoke execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, uuid) from public, service_role;
grant execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text, text, uuid) to service_role;
