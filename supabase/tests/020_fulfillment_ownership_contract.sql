begin;

select plan(18);

select ok(
  to_regprocedure('public.list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)') is not null,
  'claim-aware fulfillment listing RPC exists'
);

select ok(
  to_regprocedure('public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,uuid)') is not null,
  'session-bound claim RPC exists'
);

select ok(
  to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,uuid)') is not null,
  'session-bound completion RPC exists'
);

select ok(
  to_regprocedure('public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)') is not null,
  'legacy claim implementation remains addressable only for compatibility'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)',
    'EXECUTE'
  ) = false,
  'legacy unbound claim RPC is not executable by service_role'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)',
    'EXECUTE'
  ) = false,
  'legacy unbound completion RPC is not executable by service_role'
);

insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values
  (20001001, 'primary', true, false),
  (20001002, 'backup', true, true);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000002001', 20002001);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id)
values (
  '00000000-0000-0000-0000-000000002011',
  '00000000-0000-0000-0000-000000002001',
  'BEP20',
  '0x0000000000000000000000000000000000002001',
  '0x0000000000000000000000000000000000002001',
  'VERIFIED',
  'Fulfillment ownership test',
  'QR-2001'
);

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id, network_code,
  payment_method_id, status, version
)
select
  '00000000-0000-0000-0000-000000002021',
  'ORD-2001',
  '00000000-0000-0000-0000-000000002001',
  '00000000-0000-0000-0000-000000002011',
  'BEP20',
  id,
  'APPROVED',
  1
from payment_methods
where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, exchange_rate,
  local_amount, rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000002021',
  100, 10, 10, 0.15, 89.85, 'USD', null, 100, 'test', 1
);

select is(
  (select count(*)::integer
     from list_admin_fulfillment_orders(20001001, 'primary', 0, 5)
    where internal_order_id = '00000000-0000-0000-0000-000000002021'
      and fulfillment_claimed_by is null),
  1,
  'unclaimed approved order is listed without an owner'
);

insert into admin_sessions (id, admin_telegram_user_id, expires_at)
values
  ('00000000-0000-0000-0000-000000002031', 20001001, now() + interval '10 minutes'),
  ('00000000-0000-0000-0000-000000002032', 20001002, now() + interval '10 minutes');

select lives_ok($$
  select * from claim_order_fulfillment(
    '00000000-0000-0000-0000-000000002021',
    1,
    20001001,
    'primary',
    'fulfillment-claim-2001',
    '00000000-0000-0000-0000-000000002031'
  )
$$, 'first administrator can atomically claim the order');

select is(
  (select version from orders where internal_order_id = '00000000-0000-0000-0000-000000002021'),
  2::bigint,
  'claim advances the authoritative order version'
);

select is(
  (select fulfillment_claimed_by
     from list_admin_fulfillment_orders(20001002, 'backup', 0, 5)
    where internal_order_id = '00000000-0000-0000-0000-000000002021'),
  20001001::bigint,
  'listing exposes the authoritative claim owner to another administrator'
);

select throws_ok($$
  select * from claim_order_fulfillment(
    '00000000-0000-0000-0000-000000002021',
    2,
    20001002,
    'backup',
    'fulfillment-claim-2002',
    '00000000-0000-0000-0000-000000002032'
  )
$$, 'P0001', 'order already has an active fulfillment claim', 'a second administrator cannot claim an owned order');

select throws_ok($$
  select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002021',
    1,
    20001001,
    'primary',
    'fulfillment-stale-complete',
    '00000000-0000-0000-0000-000000002031'
  )
$$, 'P0001', 'stale order version', 'a pre-claim completion callback is rejected as stale');

select throws_ok($$
  select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002021',
    2,
    20001002,
    'backup',
    'fulfillment-wrong-owner',
    '00000000-0000-0000-0000-000000002032'
  )
$$, 'P0001', 'fulfillment claim belongs to another admin', 'a non-owner cannot complete the order');

select lives_ok($$
  select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002021',
    2,
    20001001,
    'primary',
    'fulfillment-complete-2001',
    '00000000-0000-0000-0000-000000002031'
  )
$$, 'the claim owner can complete with the current version and fresh session');

select is(
  (select status::text from orders where internal_order_id = '00000000-0000-0000-0000-000000002021'),
  'COMPLETED',
  'successful completion changes the order to COMPLETED'
);

select is(
  (select version from orders where internal_order_id = '00000000-0000-0000-0000-000000002021'),
  3::bigint,
  'successful completion advances the version exactly once'
);

select is(
  (select count(*)::integer
     from order_fulfillment_claims
    where internal_order_id = '00000000-0000-0000-0000-000000002021'),
  0,
  'completion removes the active claim'
);

select is(
  (select count(*)::integer
     from audit_logs
    where target_id = '00000000-0000-0000-0000-000000002021'
      and action in ('order.fulfillment_claimed','order.fulfillment_completed')),
  2,
  'claim and completion both create audit events'
);

select * from finish();
rollback;
