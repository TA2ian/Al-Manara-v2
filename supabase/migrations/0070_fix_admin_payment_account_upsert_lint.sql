-- Resolve the pre-existing PL/pgSQL ambiguity in the ShamCash upsert.
-- The function exposes a RETURNS TABLE column named "currency"; PostgreSQL's
-- default variable conflict mode otherwise treats the ON CONFLICT target as
-- ambiguous. Keep the existing API and mutation semantics unchanged.
create or replace function upsert_admin_payment_account(
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
#variable_conflict use_column
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

