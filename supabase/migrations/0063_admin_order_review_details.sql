-- Read-only admin review detail boundary.
-- Requires an authoritative admin actor and a fresh, non-revoked session.
-- Receipt evidence remains data only; this function never approves an order.

create or replace function get_admin_order_review_details(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_order_id uuid,
    p_session_id uuid
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    user_telegram_id bigint,
    network_code network_code,
    requested_amount numeric(24,9),
    payment_currency currency_code,
    local_amount numeric(24,9),
    receipt_submission_id uuid,
    receipt_attempt_number integer,
    receipt_input_type text,
    receipt_processing_status text,
    receipt_linkage_status text,
    receipt_telegram_file_id text,
    receipt_mime_type text,
    receipt_submitted_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_registered_actor_type admin_actor_type;
begin
    if p_admin_telegram_user_id is null
       or p_admin_telegram_user_id < 1
       or p_actor_type is null
       or p_order_id is null
       or p_session_id is null then
        raise exception 'invalid admin review details input';
    end if;

    select au.actor_type
      into v_registered_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;

    if not found or v_registered_actor_type <> p_actor_type then
        raise exception 'admin is not enabled';
    end if;

    if not exists (
        select 1
          from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_admin_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    return query
    select
        o.internal_order_id,
        o.public_order_code,
        o.status,
        o.version,
        u.telegram_user_id,
        o.network_code,
        fs.requested_amount,
        fs.payment_currency,
        fs.local_amount,
        r.id,
        r.attempt_number,
        r.input_type,
        r.processing_status,
        r.linkage_status,
        r.telegram_file_id,
        r.mime_type,
        r.submitted_at
    from orders o
    join users u on u.id = o.user_id
    left join order_financial_snapshots fs
      on fs.internal_order_id = o.internal_order_id
    left join lateral (
        select rs.*
          from receipt_submissions rs
         where rs.internal_order_id = o.internal_order_id
           and rs.source = 'customer'
         order by rs.attempt_number desc, rs.submitted_at desc, rs.id desc
         limit 1
    ) r on true
    where o.internal_order_id = p_order_id
    limit 1;

    if not found then
        raise exception 'order not found';
    end if;
end;
$$;

revoke all on function get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid) from public, anon, authenticated;
grant execute on function get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid) to service_role;
