begin;

select plan(9);

select ok(
  to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,uuid,text)') is not null,
  'manual-reference completion RPC exists'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,uuid)',
    'EXECUTE'
  ) = false,
  'old completion RPC is disabled'
);

insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values (21001001, 'primary', true, false);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000002101', 21002001);

insert into wallets (
  id, user_id, network_code, address, normalized_address, status, label
) values (
  '00000000-0000-0000-0000-000000002111',
  '00000000-0000-0000-0000-000000002101',
  'BEP20',
  '0x0000000000000000000000000000000000002101',
  '0x0000000000000000000000000000000000002101',
  'VERIFIED',
  'manual test'
);

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id,
  network_code, payment_method_id, status, version
)
select
  '00000000-0000-0000-0000-000000002121',
  'ORD-2101',
  '00000000-0000-0000-0000-000000002101',
  '00000000-0000-0000-0000-000000002111',
  'BEP20',
  id,
  'APPROVED',
  1
from payment_methods
where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, local_amount,
  rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000002121',
  100, 10, 10, 0.15, 89.85, 'USD', 100, 'test', 1
);

insert into admin_sessions (id, admin_telegram_user_id, expires_at)
values (
  '00000000-0000-0000-0000-000000002131',
  21001001,
  now() + interval '10 minutes'
);

select lives_ok(
  $$
  select * from claim_order_fulfillment(
    '00000000-0000-0000-0000-000000002121',
    1,
    21001001,
    'primary',
    'claim-2101',
    '00000000-0000-0000-0000-000000002131'
  )
  $$,
  'claim succeeds'
);

select lives_ok(
  $$
  select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002121',
    2,
    21001001,
    'primary',
    'complete-2101',
    '00000000-0000-0000-0000-000000002131',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
  )
  $$,
  'completion records manual transfer reference'
);

select is(
  (
    select manual_usdt_transfer_reference
    from orders
    where internal_order_id = '00000000-0000-0000-0000-000000002121'
  ),
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'transfer reference is persisted'
);

select is(
  (
    select status::text
    from orders
    where internal_order_id = '00000000-0000-0000-0000-000000002121'
  ),
  'COMPLETED',
  'order completes'
);

select is(
  (
    select version
    from orders
    where internal_order_id = '00000000-0000-0000-0000-000000002121'
  ),
  3::bigint,
  'completion increments version'
);

select is(
  (
    select count(*)::integer
    from audit_logs
    where target_id = '00000000-0000-0000-0000-000000002121'
      and action = 'order.fulfillment_completed'
  ),
  1,
  'completion is audited'
);

select ok(
  (
    select net_usdt_amount
    from order_financial_snapshots
    where internal_order_id = '00000000-0000-0000-0000-000000002121'
  ) = 89.85,
  'snapshot retains net USDT amount for manual transfer'
);

select * from finish();
rollback;
