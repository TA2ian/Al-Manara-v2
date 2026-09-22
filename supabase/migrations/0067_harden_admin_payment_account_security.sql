-- Harden ShamCash administrative management:
-- 1) every read/mutation requires a fresh, authoritative admin session;
-- 2) Backup Admin is accepted only when the DB marks it emergency_only;
-- 3) every mutation requires a one-time, short-lived confirmation created by the
--    application immediately before the Telegram confirmation button is shown;
-- 4) confirmation is bound to admin, actor type, session, operation and a
--    SHA-256 request fingerprint and is atomically consumed by the mutation RPC.

create table if not exists admin_action_confirmations (
    id uuid primary key default gen_random_uuid(),
    admin_telegram_user_id bigint not null,
    actor_type admin_actor_type not null,
    session_id uuid not null references admin_sessions(id) on delete restrict,
    operation text not null,
    request_fingerprint text not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    constraint admin_action_confirmation_operation check (
        operation in (
            'admin_payment_account.upsert',
            'admin_payment_account.status'
        )
    ),
    constraint admin_action_confirmation_fingerprint check (
        request_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    constraint admin_action_confirmation_expiry check (expires_at > created_at)
);

create index if not exists admin_action_confirmations_lookup_idx
    on admin_action_confirmations(
        admin_telegram_user_id,
        actor_type,
        session_id,
        operation,
        request_fingerprint,
        expires_at
    )
    where consumed_at is null;

revoke all on table admin_action_confirmations from public, anon, authenticated;
grant select, insert, update on table admin_action_confirmations to service_role;

create or replace function create_admin_action_confirmation(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid,
    p_operation text,
    p_request_fingerprint text
)
returns table (confirmation_id uuid, expires_at timestamptz)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_confirmation_id uuid;
    v_expires timestamptz;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0 then
        raise exception 'admin identity is required';
    end if;
    if p_actor_type is null or p_session_id is null then
        raise exception 'admin session is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert', 'admin_payment_account.status', 'fulfillment.complete') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;

    if not validate_admin_session(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    v_expires := now() + interval '90 seconds';

    insert into admin_action_confirmations(
        admin_telegram_user_id,
        actor_type,
        session_id,
        operation,
        request_fingerprint,
        expires_at
    )
    values (
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_operation,
        p_request_fingerprint,
        v_expires
    )
    returning id, admin_action_confirmations.expires_at
      into v_confirmation_id, v_expires;

    insert into audit_logs(
        actor_telegram_user_id,
        actor_kind,
        actor_type,
        action,
        target_type,
        target_id,
        confirmation_id,
        metadata
    )
    values (
        p_admin_telegram_user_id,
        'admin',
        p_actor_type,
        'admin.action_confirmation.created',
        'admin_action_confirmation',
        v_confirmation_id::text,
        v_confirmation_id,
        jsonb_build_object(
            'operation', p_operation,
            'expires_at', v_expires
        )
    );

    return query select v_confirmation_id, v_expires;
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
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_changed boolean;
begin
    if p_admin_telegram_user_id is null or p_admin_telegram_user_id <= 0 then
        raise exception 'admin identity is required';
    end if;
    if p_actor_type is null or p_session_id is null or p_confirmation_id is null then
        raise exception 'admin confirmation is required';
    end if;
    if p_operation not in ('admin_payment_account.upsert', 'admin_payment_account.status') then
        raise exception 'unsupported admin confirmation operation';
    end if;
    if p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid admin confirmation fingerprint';
    end if;

    if not validate_admin_session(
        p_admin_telegram_user_id,
        p_actor_type,
        p_session_id
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    update admin_action_confirmations
       set consumed_at = now()
     where id = p_confirmation_id
       and admin_telegram_user_id = p_admin_telegram_user_id
       and actor_type = p_actor_type
       and session_id = p_session_id
       and operation = p_operation
       and request_fingerprint = p_request_fingerprint
       and consumed_at is null
       and expires_at > now();

    v_changed := found;

    if not v_changed then
        raise exception 'admin action confirmation is invalid, expired, or already consumed';
    end if;

    return true;
end;
$$;

drop function if exists list_admin_payment_accounts(bigint, admin_actor_type);
drop function if exists upsert_admin_payment_account(bigint, admin_actor_type, currency_code, text, text, text);
drop function if exists set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean);

create function list_admin_payment_accounts(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid
)
returns table (
    id uuid,
    payment_method_code text,
    payment_method_status payment_method_status,
    currency currency_code,
    account_name text,
    account_number text,
    qr_image_file_id text,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
begin
    if not validate_admin_session(p_telegram_user_id, p_actor_type, p_session_id) then
        raise exception 'admin session is invalid or expired';
    end if;

    return query
    select apa.id,
           pm.code,
           pm.status,
           apa.currency,
           apa.account_name,
           apa.account_number,
           apa.qr_image_file_id,
           apa.is_active,
           apa.updated_at
      from admin_payment_accounts apa
      join payment_methods pm on pm.id = apa.payment_method_id
     where pm.code = 'SHAM_CASH'
     order by apa.currency, apa.updated_at desc;
end;
$$;

create function upsert_admin_payment_account(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_currency currency_code,
    p_account_name text,
    p_account_number text,
    p_qr_image_file_id text,
    p_session_id uuid,
    p_confirmation_id uuid,
    p_request_fingerprint text
)
returns table (
    id uuid,
    currency currency_code,
    account_name text,
    account_number text,
    qr_image_file_id text,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_payment_method_id uuid;
    v_id uuid;
begin
    perform consume_admin_action_confirmation(
        p_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_confirmation_id,
        'admin_payment_account.upsert',
        p_request_fingerprint
    );

    if p_currency is null then
        raise exception 'payment currency is required';
    end if;
    if length(btrim(coalesce(p_account_name, ''))) not between 2 and 100 then
        raise exception 'payment account name length is invalid';
    end if;
    if length(btrim(coalesce(p_account_number, ''))) not between 5 and 150 then
        raise exception 'payment account number length is invalid';
    end if;
    if length(btrim(coalesce(p_qr_image_file_id, ''))) = 0 then
        raise exception 'qr image file id is required';
    end if;

    select pm.id
      into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH'
       and pm.status = 'ENABLED';

    if not found then
        raise exception 'SHAM_CASH payment method is disabled';
    end if;

    insert into admin_payment_accounts (
        payment_method_id,
        currency,
        account_name,
        account_number,
        qr_image_file_id,
        is_active
    )
    values (
        v_payment_method_id,
        p_currency,
        btrim(p_account_name),
        btrim(p_account_number),
        btrim(p_qr_image_file_id),
        true
    )
    on conflict (payment_method_id, currency)
    do update set
        account_name = excluded.account_name,
        account_number = excluded.account_number,
        qr_image_file_id = excluded.qr_image_file_id,
        is_active = true,
        updated_at = now()
    returning admin_payment_accounts.id into v_id;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_kind,
        actor_type,
        action,
        target_type,
        target_id,
        confirmation_id,
        old_value,
        new_value,
        metadata
    )
    values (
        p_telegram_user_id,
        'admin',
        p_actor_type,
        'admin_payment_account.updated',
        'admin_payment_account',
        v_id::text,
        p_confirmation_id,
        null,
        jsonb_build_object(
            'currency', p_currency,
            'account_name', btrim(p_account_name),
            'account_number', btrim(p_account_number),
            'qr_image_file_id', btrim(p_qr_image_file_id),
            'is_active', true
        ),
        jsonb_build_object('request_fingerprint', p_request_fingerprint)
    );

    return query
    select apa.id,
           apa.currency,
           apa.account_name,
           apa.account_number,
           apa.qr_image_file_id,
           apa.is_active,
           apa.updated_at
      from admin_payment_accounts apa
     where apa.id = v_id;
end;
$$;

create function set_admin_payment_account_active(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_currency currency_code,
    p_is_active boolean,
    p_session_id uuid,
    p_confirmation_id uuid,
    p_request_fingerprint text
)
returns table (
    id uuid,
    currency currency_code,
    account_name text,
    account_number text,
    qr_image_file_id text,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_payment_method_id uuid;
    v_id uuid;
    v_old_is_active boolean;
begin
    perform consume_admin_action_confirmation(
        p_telegram_user_id,
        p_actor_type,
        p_session_id,
        p_confirmation_id,
        'admin_payment_account.status',
        p_request_fingerprint
    );

    select pm.id
      into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH';

    if not found then
        raise exception 'SHAM_CASH payment method not found';
    end if;

    select apa.id, apa.is_active
      into v_id, v_old_is_active
      from admin_payment_accounts apa
     where apa.payment_method_id = v_payment_method_id
       and apa.currency = p_currency
     for update;

    if not found then
        raise exception 'admin payment account not found';
    end if;

    update admin_payment_accounts apa
       set is_active = p_is_active,
           updated_at = now()
     where apa.id = v_id;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_kind,
        actor_type,
        action,
        target_type,
        target_id,
        confirmation_id,
        old_value,
        new_value,
        metadata
    )
    values (
        p_telegram_user_id,
        'admin',
        p_actor_type,
        'admin_payment_account.status_changed',
        'admin_payment_account',
        v_id::text,
        p_confirmation_id,
        jsonb_build_object('currency', p_currency, 'is_active', v_old_is_active),
        jsonb_build_object('currency', p_currency, 'is_active', p_is_active),
        jsonb_build_object('request_fingerprint', p_request_fingerprint)
    );

    return query
    select apa.id,
           apa.currency,
           apa.account_name,
           apa.account_number,
           apa.qr_image_file_id,
           apa.is_active,
           apa.updated_at
      from admin_payment_accounts apa
     where apa.id = v_id;
end;
$$;

revoke all on function create_admin_action_confirmation(bigint, admin_actor_type, uuid, text, text) from public, anon, authenticated;
revoke all on function consume_admin_action_confirmation(bigint, admin_actor_type, uuid, uuid, text, text) from public, anon, authenticated;
revoke all on function list_admin_payment_accounts(bigint, admin_actor_type, uuid) from public, anon, authenticated;
revoke all on function upsert_admin_payment_account(bigint, admin_actor_type, currency_code, text, text, text, uuid, uuid, text) from public, anon, authenticated;
revoke all on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean, uuid, uuid, text) from public, anon, authenticated;

grant execute on function create_admin_action_confirmation(bigint, admin_actor_type, uuid, text, text) to service_role;
grant execute on function consume_admin_action_confirmation(bigint, admin_actor_type, uuid, uuid, text, text) to service_role;
grant execute on function list_admin_payment_accounts(bigint, admin_actor_type, uuid) to service_role;
grant execute on function upsert_admin_payment_account(bigint, admin_actor_type, currency_code, text, text, text, uuid, uuid, text) to service_role;
grant execute on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean, uuid, uuid, text) to service_role;
