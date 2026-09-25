-- Require a one-time, operation-bound confirmation for every mutating admin review.
-- The existing session requirement remains mandatory; confirmation adds a second
-- explicit step for approve/reject/clarify decisions.

alter table admin_action_confirmations
    drop constraint if exists admin_action_confirmation_operation;

alter table admin_action_confirmations
    add constraint admin_action_confirmation_operation check (
        operation in (
            'admin_payment_account.upsert',
            'admin_payment_account.status',
            'fulfillment.complete',
            'order.reopen_receipt',
            'order.admin_review'
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
    if p_operation not in (
        'admin_payment_account.upsert',
        'admin_payment_account.status',
        'fulfillment.complete',
        'order.reopen_receipt',
        'order.admin_review'
    ) then
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
    if p_operation not in (
        'admin_payment_account.upsert',
        'admin_payment_account.status',
        'fulfillment.complete',
        'order.reopen_receipt',
        'order.admin_review'
    ) then
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

drop function if exists admin_review_order_transition_idempotent(
    uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid
);

create function admin_review_order_transition_idempotent(
    p_order_id uuid,
    p_target_status order_status,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text,
    p_event_payload jsonb,
    p_session_id uuid,
    p_confirmation_id uuid,
    p_request_fingerprint text
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
language plpgsql security invoker set search_path = public
as $$
declare
    v_existing jsonb;
    v_order orders%rowtype;
    v_registered_actor_type admin_actor_type;
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
       or p_confirmation_id is null
       or p_target_status not in ('APPROVED','REJECTED','CLARIFICATION_REQUIRED')
       or p_idempotency_key is null
       or length(btrim(p_idempotency_key)) = 0
       or length(btrim(p_idempotency_key)) > 128
       or p_request_fingerprint is null
       or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin review transition input';
    end if;

    if p_target_status in ('REJECTED','CLARIFICATION_REQUIRED')
       and (length(v_reason) < 5 or length(v_reason) > 1000) then
        raise exception 'review reason is required';
    end if;

    select au.actor_type
      into v_registered_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;

    if not found then
        raise exception 'admin is not enabled';
    end if;
    if v_registered_actor_type <> p_actor_type then
        raise exception 'admin actor type mismatch';
    end if;

    if not validate_admin_session(p_admin_telegram_user_id,p_actor_type,p_session_id) then
        raise exception 'admin session is invalid or expired';
    end if;

    insert into order_transition_idempotency (
        idempotency_key,
        internal_order_id,
        target_status,
        expected_version,
        actor_telegram_user_id,
        actor_type,
        result
    ) values (
        btrim(p_idempotency_key),
        p_order_id,
        p_target_status,
        p_expected_version,
        p_admin_telegram_user_id,
        p_actor_type,
        jsonb_build_object('finalized', false)
    ) on conflict (idempotency_key) do nothing;

    select oti.result
      into v_existing
      from order_transition_idempotency oti
     where oti.idempotency_key = btrim(p_idempotency_key)
     for update;

    if not found then
        raise exception 'admin review idempotency reservation disappeared';
    end if;

    if coalesce((v_existing->>'finalized')::boolean, true) then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'target_status')::order_status <> p_target_status
           or (v_existing->>'expected_version')::bigint <> p_expected_version
           or (v_existing->>'actor_telegram_user_id')::bigint <> p_admin_telegram_user_id
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
            (v_existing->>'target_status')::order_status,
            (v_existing->>'transitioned_at')::timestamptz;
        return;
    end if;

    perform consume_admin_action_confirmation(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_confirmation_id,
        'order.admin_review',
        p_request_fingerprint
    );

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
        actor_kind,
        actor_type,
        action,
        target_type,
        target_id,
        old_value,
        new_value,
        metadata,
        confirmation_id
    ) values (
        p_admin_telegram_user_id,
        'admin',
        p_actor_type,
        'order.admin_reviewed',
        'order',
        p_order_id::text,
        jsonb_build_object('status', v_before, 'version', p_expected_version),
        jsonb_build_object('status', p_target_status, 'version', p_expected_version + 1),
        coalesce(p_event_payload, '{}'::jsonb) || jsonb_build_object('session_id', p_session_id::text),
        p_confirmation_id
    );

    update order_transition_idempotency
       set result = jsonb_build_object(
           'finalized', true,
           'internal_order_id', p_order_id,
           'public_order_code', v_order.public_order_code,
           'status', p_target_status,
           'version', p_expected_version + 1,
           'state_before', v_before,
           'target_status', v_after,
           'expected_version', p_expected_version,
           'actor_telegram_user_id', p_admin_telegram_user_id,
           'actor_type', p_actor_type,
           'transitioned_at', v_transitioned_at
       )
     where idempotency_key = btrim(p_idempotency_key);

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

revoke all on function admin_review_order_transition_idempotent(
    uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid,uuid,text
) from public,anon,authenticated;
grant execute on function admin_review_order_transition_idempotent(
    uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid,uuid,text
) to service_role;
