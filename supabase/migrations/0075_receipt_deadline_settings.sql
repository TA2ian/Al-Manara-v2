-- Separate the quote price-validity window from the customer receipt window.
alter table settings add column if not exists receipt_submission_window_minutes integer not null default 60;
update settings set absolute_tolerance=0.01 where id=true;
alter table settings drop constraint if exists settings_receipt_window_valid;
alter table settings add constraint settings_receipt_window_valid check (receipt_submission_window_minutes between 1 and 90);

create or replace function get_receipt_submission_window()
returns table (receipt_submission_window_minutes integer)
language sql security invoker set search_path = public
as $$ select receipt_submission_window_minutes from settings where id=true; $$;
revoke all on function get_receipt_submission_window() from public, anon, authenticated;
grant execute on function get_receipt_submission_window() to service_role;

create or replace function update_receipt_submission_window(
    p_admin_telegram_user_id bigint, p_actor_type admin_actor_type,
    p_confirmation_id uuid, p_request_fingerprint text, p_minutes integer
) returns integer
language plpgsql security invoker set search_path = public
as $$
declare v_confirmation admin_action_confirmations%rowtype; v_actor_type admin_actor_type;
        v_old_minutes integer;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0 or p_actor_type is null or p_confirmation_id is null then
        raise exception 'admin confirmation is required';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then raise exception 'invalid request fingerprint'; end if;
    if p_minutes is null or p_minutes < 1 or p_minutes > 90 then raise exception 'receipt submission window must be between 1 and 90 minutes'; end if;

    select au.actor_type into v_actor_type from admin_users au
     where au.telegram_user_id=p_admin_telegram_user_id and au.enabled and (au.actor_type='primary' or au.emergency_only) for share;
    if not found or v_actor_type <> p_actor_type then raise exception 'admin is not enabled'; end if;

    select * into v_confirmation from admin_action_confirmations c
     where c.id=p_confirmation_id and c.admin_telegram_user_id=p_admin_telegram_user_id
       and c.actor_type=p_actor_type and c.operation='admin_settings.receipt_window'
       and c.request_fingerprint=p_request_fingerprint and c.consumed_at is null and c.expires_at > now()
     for update;
    if not found then raise exception 'admin setting confirmation is invalid, expired, or already consumed'; end if;
    if not validate_admin_session(v_confirmation.admin_telegram_user_id,v_confirmation.actor_type,v_confirmation.session_id) then
        raise exception 'admin session is invalid or expired';
    end if;

    select receipt_submission_window_minutes into v_old_minutes from settings where id=true for update;
    if not found then raise exception 'settings row is unavailable'; end if;

    update admin_action_confirmations set consumed_at=now() where id=p_confirmation_id and consumed_at is null;
    if not found then raise exception 'admin setting confirmation was already consumed'; end if;

    update settings set receipt_submission_window_minutes=p_minutes, updated_at=now() where id=true;

    insert into audit_logs(actor_telegram_user_id,actor_kind,actor_type,action,target_type,target_id,old_value,new_value,confirmation_id,metadata)
    values(p_admin_telegram_user_id,'admin',p_actor_type,'admin.settings.receipt_window.updated','settings','global',
           jsonb_build_object('receipt_submission_window_minutes',v_old_minutes),
           jsonb_build_object('receipt_submission_window_minutes',p_minutes),
           p_confirmation_id,jsonb_build_object('source','telegram_admin_settings'));
    return p_minutes;
end;
$$;
revoke all on function update_receipt_submission_window(bigint,admin_actor_type,uuid,text,integer) from public, anon, authenticated;
grant execute on function update_receipt_submission_window(bigint,admin_actor_type,uuid,text,integer) to service_role;

alter table admin_action_confirmations drop constraint if exists admin_action_confirmation_operation;
alter table admin_action_confirmations add constraint admin_action_confirmation_operation check (
 operation in ('admin_payment_account.upsert','admin_payment_account.status','fulfillment.complete',
              'order.reopen_receipt','order.admin_review','admin_settings.receipt_window'));

create or replace function create_admin_action_confirmation(
 p_admin_telegram_user_id bigint,p_actor_type admin_actor_type,p_session_id uuid,p_operation text,p_request_fingerprint text)
returns table(confirmation_id uuid,expires_at timestamptz)
language plpgsql security invoker set search_path=public
as $$
declare v_confirmation_id uuid; v_expires timestamptz;
begin
 if p_admin_telegram_user_id is null or p_admin_telegram_user_id<=0 or p_actor_type is null or p_session_id is null then raise exception 'admin session is required'; end if;
 if p_operation not in ('admin_payment_account.upsert','admin_payment_account.status','fulfillment.complete','order.reopen_receipt','order.admin_review','admin_settings.receipt_window') then raise exception 'unsupported admin confirmation operation'; end if;
 if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then raise exception 'invalid admin confirmation fingerprint'; end if;
 if not validate_admin_session(p_admin_telegram_user_id,p_actor_type,p_session_id) then raise exception 'admin session is invalid or expired'; end if;
 v_expires=now()+interval '90 seconds';
 insert into admin_action_confirmations(admin_telegram_user_id,actor_type,session_id,operation,request_fingerprint,expires_at)
 values(p_admin_telegram_user_id,p_actor_type,p_session_id,p_operation,p_request_fingerprint,v_expires)
 returning id,admin_action_confirmations.expires_at into v_confirmation_id,v_expires;
 insert into audit_logs(actor_telegram_user_id,actor_kind,actor_type,action,target_type,target_id,confirmation_id,metadata)
 values(p_admin_telegram_user_id,'admin',p_actor_type,'admin.action_confirmation.created','admin_action_confirmation',
        v_confirmation_id::text,v_confirmation_id,jsonb_build_object('operation',p_operation,'expires_at',v_expires));
 return query select v_confirmation_id,v_expires;
end;
$$;
