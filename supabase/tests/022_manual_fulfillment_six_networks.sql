begin;

select plan(26);

select is(
  (select count(*)::integer from network_configs
   where enabled and code in ('BEP20','TRC20','ARB','ETH','SOL','POLYGON')),
  6,
  'all six operational networks are enabled'
);

select is((select network_fee_amount from network_configs where code='BEP20'), 0.150000000::numeric, 'BEP20 fee is 0.15 USDT');
select is((select network_fee_amount from network_configs where code='TRC20'), 1.500000000::numeric, 'TRC20 fee is 1.50 USDT');
select is((select network_fee_amount from network_configs where code='ARB'), 0.150000000::numeric, 'ARB fee is 0.15 USDT');
select is((select network_fee_amount from network_configs where code='ETH'), 0.800000000::numeric, 'ETH fee is 0.80 USDT');
select is((select network_fee_amount from network_configs where code='SOL'), 1.000000000::numeric, 'SOL fee is 1.00 USDT');
select is((select network_fee_amount from network_configs where code='POLYGON'), 0.200000000::numeric, 'POLYGON fee is 0.20 USDT');

insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values (22001001, 'primary', true, false);

insert into admin_sessions (id, admin_telegram_user_id, expires_at)
values ('00000000-0000-0000-0000-000000002231', 22001001, now() + interval '10 minutes');

insert into users (id, telegram_user_id) values
  ('00000000-0000-0000-0000-000000002201', 22002001),
  ('00000000-0000-0000-0000-000000002202', 22002002),
  ('00000000-0000-0000-0000-000000002203', 22002003),
  ('00000000-0000-0000-0000-000000002204', 22002004),
  ('00000000-0000-0000-0000-000000002205', 22002005),
  ('00000000-0000-0000-0000-000000002206', 22002006);

insert into wallets (
  id, user_id, network_code, address, normalized_address, status, qr_image_file_id, label
) values
  ('00000000-0000-0000-0000-000000002211','00000000-0000-0000-0000-000000002201','BEP20','0x0000000000000000000000000000000000002201','0x0000000000000000000000000000000000002201','VERIFIED','qr-2201','six-network test'),
  ('00000000-0000-0000-0000-000000002212','00000000-0000-0000-0000-000000002202','TRC20','T9yD14Nj9j7xAB4dbGeiX9h8unkM4Jx7nQ','T9yD14Nj9j7xAB4dbGeiX9h8unkM4Jx7nQ','VERIFIED','qr-2202','six-network test'),
  ('00000000-0000-0000-0000-000000002213','00000000-0000-0000-0000-000000002203','ARB','0x0000000000000000000000000000000000002203','0x0000000000000000000000000000000000002203','VERIFIED','qr-2203','six-network test'),
  ('00000000-0000-0000-0000-000000002214','00000000-0000-0000-0000-000000002204','ETH','0x0000000000000000000000000000000000002204','0x0000000000000000000000000000000000002204','VERIFIED','qr-2204','six-network test'),
  ('00000000-0000-0000-0000-000000002215','00000000-0000-0000-0000-000000002205','SOL','11111111111111111111111111111111','11111111111111111111111111111111','VERIFIED','qr-2205','six-network test'),
  ('00000000-0000-0000-0000-000000002216','00000000-0000-0000-0000-000000002206','POLYGON','0x0000000000000000000000000000000000002206','0x0000000000000000000000000000000000002206','VERIFIED','qr-2206','six-network test');

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id, network_code,
  payment_method_id, status, version
)
select
  v.order_id, v.code, v.user_id, v.wallet_id, v.network, pm.id, 'APPROVED', 1
from (
  values
    ('00000000-0000-0000-0000-000000002221'::uuid,'ORD-2201','00000000-0000-0000-0000-000000002201'::uuid,'00000000-0000-0000-0000-000000002211'::uuid,'BEP20'::network_code),
    ('00000000-0000-0000-0000-000000002222'::uuid,'ORD-2202','00000000-0000-0000-0000-000000002202'::uuid,'00000000-0000-0000-0000-000000002212'::uuid,'TRC20'::network_code),
    ('00000000-0000-0000-0000-000000002223'::uuid,'ORD-2203','00000000-0000-0000-0000-000000002203'::uuid,'00000000-0000-0000-0000-000000002213'::uuid,'ARB'::network_code),
    ('00000000-0000-0000-0000-000000002224'::uuid,'ORD-2204','00000000-0000-0000-0000-000000002204'::uuid,'00000000-0000-0000-0000-000000002214'::uuid,'ETH'::network_code),
    ('00000000-0000-0000-0000-000000002225'::uuid,'ORD-2205','00000000-0000-0000-0000-000000002205'::uuid,'00000000-0000-0000-0000-000000002215'::uuid,'SOL'::network_code),
    ('00000000-0000-0000-0000-000000002226'::uuid,'ORD-2206','00000000-0000-0000-0000-000000002206'::uuid,'00000000-0000-0000-0000-000000002216'::uuid,'POLYGON'::network_code)
) as v(order_id, code, user_id, wallet_id, network)
cross join (select id from payment_methods where code='SHAM_CASH') pm;

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, local_amount,
  rounding_policy_version, network_config_version
)
select
  o.internal_order_id,
  100,
  10,
  10,
  nc.network_fee_amount,
  round(100 - 10 - nc.network_fee_amount, 9),
  'USD',
  100,
  'test',
  nc.config_version
from orders o
join network_configs nc on nc.code=o.network_code
where o.public_order_code like 'ORD-220%';

insert into order_fulfillment_claims (internal_order_id, admin_telegram_user_id, claimed_at)
select internal_order_id, 22001001, now()
from orders where public_order_code like 'ORD-220%';

create temporary table test_fulfillment_confirmations (
  public_order_code text primary key,
  confirmation_id uuid not null,
  request_fingerprint text not null
) on commit drop;

insert into test_fulfillment_confirmations (public_order_code, confirmation_id, request_fingerprint)
select v.code, c.confirmation_id, v.fingerprint
from (
  values
    ('ORD-2201', repeat('a',64)),
    ('ORD-2202', repeat('b',64)),
    ('ORD-2203', repeat('c',64)),
    ('ORD-2204', repeat('d',64)),
    ('ORD-2205', repeat('e',64)),
    ('ORD-2206', repeat('f',64))
) as v(code, fingerprint)
cross join lateral create_admin_action_confirmation(
  22001001, 'primary', '00000000-0000-0000-0000-000000002231',
  'fulfillment.complete', v.fingerprint
) c;

select throws_ok(
  $$select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002221', 1, 22001001, 'primary',
    'complete-2201', '00000000-0000-0000-0000-000000002231', repeat('a',64),
    (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2201'),
    repeat('0',64)
  ))$$,
  'P0001',
  'admin action confirmation is invalid, expired, or already consumed',
  'mismatched fulfillment fingerprint is rejected');

select throws_ok(
  $$select * from complete_order_fulfillment(
    '00000000-0000-0000-0000-000000002221', 1, 22001001, 'primary',
    'complete-no-confirmation', '00000000-0000-0000-0000-000000002231', repeat('1',64),
    null, repeat('1',64)
  )$$,
  'P0001',
  'fulfillment confirmation is required',
  'completion without confirmation is rejected');

select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002221', 1, 22001001, 'primary', 'complete-2201', '00000000-0000-0000-0000-000000002231', repeat('a',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2201'), repeat('a',64))$$, 'BEP20 completion succeeds');
select throws_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002221', 1, 22001001, 'primary', 'complete-2201-replay', '00000000-0000-0000-0000-000000002231', repeat('a',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2201'), repeat('a',64))$$, 'P0001', 'admin action confirmation is invalid, expired, or already consumed', 'consumed fulfillment confirmation cannot be replayed');
select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002222', 1, 22001001, 'primary', 'complete-2202', '00000000-0000-0000-0000-000000002231', repeat('b',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2202'), repeat('b',64))$$, 'TRC20 completion succeeds');
select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002223', 1, 22001001, 'primary', 'complete-2203', '00000000-0000-0000-0000-000000002231', repeat('c',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2203'), repeat('c',64))$$, 'ARB completion succeeds');
select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002224', 1, 22001001, 'primary', 'complete-2204', '00000000-0000-0000-0000-000000002231', repeat('d',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2204'), repeat('d',64))$$, 'ETH completion succeeds');
select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002225', 1, 22001001, 'primary', 'complete-2205', '00000000-0000-0000-0000-000000002231', repeat('e',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2205'), repeat('e',64))$$, 'SOL completion succeeds');
select lives_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002226', 1, 22001001, 'primary', 'complete-2206', '00000000-0000-0000-0000-000000002231', repeat('f',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2206'), repeat('f',64))$$, 'POLYGON completion succeeds');

select is((select count(*)::integer from orders where public_order_code like 'ORD-220%' and status='COMPLETED'), 6, 'all six manual fulfillment orders complete');
select is((select count(*)::integer from orders where public_order_code like 'ORD-220%' and manual_usdt_transfer_reference is not null), 6, 'all six completion TXIDs are persisted');
select is((select count(*)::integer from audit_logs where target_id in (select internal_order_id::text from orders where public_order_code like 'ORD-220%') and action='order.fulfillment_completed'), 6, 'all six completions are audited');

select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002221'), 89.850000000::numeric, 'BEP20 net amount is requested less service and network fees');
select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002222'), 88.500000000::numeric, 'TRC20 net amount is requested less service and network fees');
select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002223'), 89.850000000::numeric, 'ARB net amount is requested less service and network fees');
select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002224'), 89.200000000::numeric, 'ETH net amount is requested less service and network fees');
select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002225'), 89.000000000::numeric, 'SOL net amount is requested less service and network fees');
select is((select net_usdt_amount from order_financial_snapshots where internal_order_id='00000000-0000-0000-0000-000000002226'), 89.800000000::numeric, 'POLYGON net amount is requested less service and network fees');

insert into test_fulfillment_confirmations (public_order_code, confirmation_id, request_fingerprint)
select 'ORD-2206-stale', c.confirmation_id, repeat('f',64)
from create_admin_action_confirmation(
  22001001, 'primary', '00000000-0000-0000-0000-000000002231',
  'fulfillment.complete', repeat('f',64)
) c;

select throws_ok($$select * from complete_order_fulfillment('00000000-0000-0000-0000-000000002226', 1, 22001001, 'primary', 'complete-2207', '00000000-0000-0000-0000-000000002231', repeat('f',64), (select confirmation_id from test_fulfillment_confirmations where public_order_code='ORD-2206-stale'), repeat('f',64))$$, 'P0001', 'stale order version', 'completed order rejects stale completion');

select * from finish();
rollback;
