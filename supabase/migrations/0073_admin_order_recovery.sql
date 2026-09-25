-- Controlled admin recovery: move only CLARIFICATION_REQUIRED orders back to UNDER_REVIEW.
-- This operation never changes financial snapshots, payment amounts, wallet data, or fulfillment state.

alter table admin_action_confirmations
    drop constraint if exists admin_action_confirmation_operation;

alter table admin_action_confirmations
    add constraint admin_action_confirmation_operation check (
        operation in (
            'admin_payment_account.upsert',
            'admin_payment_account.status',
            'fulfillment.complete',
            'order.recover'
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
language plpgsql security invoker set search_path = public
as $$
declare
    v_confirmation_id uuid;
    v_expires timestamptz;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0
       or p_actor_type is null or p_session_id is null then
        raise exception 'admin session is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert','admin_payment_account.status','fulfillment.complete','order.recover') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;
    if not validate_admin_session(p_admin_telegram_user_id,p_actor_type,p_session_id) then
        raise exception 'admin session is invalid or expired';
    end if;
    v_expires := now() + interval '90 seconds';
    insert into admin_action_confirmations(
        admin_telegram_user_id,actor_type,session_id,operation,request_fingerprint,expires_at
    ) values (
        p_admin_telegram_user_id,p_actor_type,p_session_id,p_operation,p_request_fingerprint,v_expires
    ) returning id,admin_action_confirmations.expires_at into v_confirmation_id,v_expires;
    insert into audit_logs(
        actor_telegram_user_id,actor_kind,actor_type,action,target_type,target_id,confirmation_id,metadata
    ) values (
        p_admin_telegram_user_id,'admin',p_actor_type,'admin.action_confirmation.created',
        'admin_action_confirmation',v_confirmation_id::text,v_confirmation_id,
        jsonb_build_object('operation',p_operation,'expires_at',v_expires)
    );
    return query select v_confirmation_id,v_expires;
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
language plpgsql security invoker set search_path = public
as $$
declare
    v_changed boolean;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0
       or p_actor_type is null or p_session_id is null or p_confirmation_id is null then
        raise exception 'admin confirmation is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert','admin_payment_account.status','fulfillment.complete','order.recover') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;
    if not validate_admin_session(p_admin_telegram_user_id,p_actor_type,p_session_id) then
        raise exception 'admin session is invalid or expired';
    end if;
    update admin_action_confirmations
       set consumed_at=now()
     where id=p_confirmation_id
       and admin_telegram_user_id=p_admin_telegram_user_id
       and actor_type=p_actor_type
       and session_id=p_session_id
       and operation=p_operation
       and request_fingerprint=p_request_fingerprint
       and consumed_at is null
       and expires_at > now();
    v_changed:=found;
    if not v_changed then
        raise exception 'admin action confirmation is invalid, expired, or already consumed';
    end if;
    return true;
end;
$$;

create or replace function admin_recover_order_to_review(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid,
    p_confirmation_id uuid,
    p_request_fingerprint text,
    p_reason text,
    p_idempotency_key text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    replayed boolean
)
language plpgsql security invoker set search_path = public
as $$
declare
    v_existing jsonb;
    v_status order_status;
    v_version bigint;
    v_code text;
    v_actor admin_actor_type;
    v_reason text := btrim(coalesce(p_reason,''));
begin
    if p_order_id is null or p_expected_version <= 0 or p_admin_telegram_user_id <= 0
       or p_actor_type is null or p_session_id is null or p_confirmation_id is null then
        raise exception 'invalid order recovery input';
    end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) not between 1 and 128 then
        raise exception 'idempotency key is invalid';
    end if;
    if v_reason !~ '^.{5,1000}$' then
        raise exception 'recovery reason is required';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid recovery fingerprint';
    end if;

    select au.actor_type into v_actor
      from admin_users au
     where au.telegram_user_id=p_admin_telegram_user_id
       and au.enabled and (au.actor_type='primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;
    if v_actor <> p_actor_type then raise exception 'admin actor type mismatch'; end if;

    if not validate_admin_session(p_admin_telegram_user_id,p_actor_type,p_session_id) then
        raise exception 'admin session is invalid or expired';
    end if;

    -- Lock the target before checking idempotency/consuming confirmation.
    -- This makes same-key concurrent recovery deterministic.
    select o.status,o.version,o.public_order_code
      into v_status,v_version,v_code
      from orders o where o.internal_order_id=p_order_id for update;
    if not found then raise exception 'order not found'; end if;

    select oti.result into v_existing
      from order_transition_idempotency oti
     where oti.idempotency_key=btrim(p_idempotency_key)
     for update;
    if found and coalesce((v_existing->>'operation')::text,'')='order.recover' then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'expected_version')::bigint <> p_expected_version
           or (v_existing->>'actor_telegram_user_id')::bigint <> p_admin_telegram_user_id then
            raise exception 'idempotency key belongs to another recovery operation';
        end if;
        return query select p_order_id,v_code,'UNDER_REVIEW'::order_status,
            (v_existing->>'version')::bigint,true;
        return;
    elsif found then
        raise exception 'idempotency key belongs to another transition';
    end if;

    perform consume_admin_action_confirmation(
        p_admin_telegram_user_id,p_actor_type,p_session_id,p_confirmation_id,
        'order.recover',p_request_fingerprint
    );

    if v_version <> p_expected_version then
        raise exception using errcode='P0001',message='stale order version',
            detail=format('expected=%s current=%s',p_expected_version,v_version);
    end if;
    if v_status <> 'CLARIFICATION_REQUIRED' then
        raise exception 'order is not eligible for recovery to review';
    end if;

    update orders as o
       set status='UNDER_REVIEW',version=o.version+1,updated_at=now()
     where o.internal_order_id=p_order_id and o.version=p_expected_version;
    if not found then raise exception 'order changed concurrently'; end if;

    insert into audit_logs(
        actor_telegram_user_id,actor_kind,actor_type,action,target_type,target_id,
        old_value,new_value,metadata,confirmation_id
    ) values (
        p_admin_telegram_user_id,'admin',v_actor,'order.recovered_to_review','order',p_order_id::text,
        jsonb_build_object('status',v_status,'version',p_expected_version),
        jsonb_build_object('status','UNDER_REVIEW','version',p_expected_version+1),
        jsonb_build_object('reason',v_reason,'session_id',p_session_id),
        p_confirmation_id
    );

    insert into order_transition_idempotency(
        idempotency_key,internal_order_id,target_status,expected_version,
        actor_telegram_user_id,actor_type,result
    ) values (
        btrim(p_idempotency_key),p_order_id,'UNDER_REVIEW',p_expected_version,
        p_admin_telegram_user_id,p_actor_type,
        jsonb_build_object(
            'operation','order.recover','internal_order_id',p_order_id,
            'public_order_code',v_code,'status','UNDER_REVIEW',
            'version',p_expected_version+1,
            'expected_version',p_expected_version,
            'actor_telegram_user_id',p_admin_telegram_user_id
        )
    );

    return query select p_order_id,v_code,'UNDER_REVIEW'::order_status,p_expected_version+1,false;
end;
$$;

revoke all on function admin_recover_order_to_review(uuid,bigint,bigint,admin_actor_type,uuid,uuid,text,text,text) from public,anon,authenticated;
grant execute on function admin_recover_order_to_review(uuid,bigint,bigint,admin_actor_type,uuid,uuid,text,text,text) to service_role;
