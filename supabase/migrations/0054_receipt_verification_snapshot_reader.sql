-- Read the authoritative order verification snapshot for the shared
-- customer/admin receipt-verification pipeline.
-- This is a read-only service boundary: it never mutates order state.

create or replace function get_receipt_verification_snapshot(p_order_id uuid)
returns table (
    order_id uuid,
    payment_currency currency_code,
    expected_payment_amount numeric(24,9),
    exchange_rate numeric(24,9),
    fee_percent numeric(9,6),
    rounding_policy_version text,
    network_code network_code,
    wallet_address text,
    expected_reference text,
    tolerance numeric(24,9)
)
language sql
security invoker
set search_path = public
as $$
    select
        o.internal_order_id,
        s.payment_currency,
        s.local_amount,
        s.exchange_rate,
        s.fee_percent,
        s.rounding_policy_version,
        o.network_code,
        w.address,
        nullif(btrim(o.shamcash_operation_number), ''),
        st.absolute_tolerance
    from orders o
    join order_financial_snapshots s
      on s.internal_order_id = o.internal_order_id
    join wallets w
      on w.id = o.wallet_id
     and w.user_id = o.user_id
    cross join settings st
    where o.internal_order_id = p_order_id
    limit 1;
$$;

revoke all on function get_receipt_verification_snapshot(uuid) from public;
grant execute on function get_receipt_verification_snapshot(uuid) to service_role;
