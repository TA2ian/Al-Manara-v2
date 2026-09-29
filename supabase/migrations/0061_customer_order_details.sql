-- Customer order details are resolved by authenticated Telegram identity and
-- public order code. Internal identifiers never enter Telegram callback data.
create or replace function get_customer_order_details(
    p_telegram_user_id bigint,
    p_public_order_code text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    network_code network_code,
    requested_amount numeric(24,9),
    payment_currency currency_code,
    local_amount numeric(24,9),
    created_at timestamptz
)
language sql
security invoker
set search_path = public
as $$
    select
        o.internal_order_id,
        o.public_order_code,
        o.status,
        o.version,
        o.network_code,
        s.requested_amount,
        s.payment_currency,
        s.local_amount,
        o.created_at
    from orders o
    join users u on u.id = o.user_id
    left join order_financial_snapshots s on s.internal_order_id = o.internal_order_id
    where u.telegram_user_id = p_telegram_user_id
      and coalesce(u.is_disabled, false) = false
      and o.public_order_code = btrim(p_public_order_code)
    limit 1;
$$;

revoke all on function get_customer_order_details(bigint, text) from public, anon, authenticated;
grant execute on function get_customer_order_details(bigint, text) to service_role;
