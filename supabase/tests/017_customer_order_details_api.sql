begin;

select plan(9);

select ok(
  to_regprocedure('public.get_customer_order_details(bigint,text)') is not null,
  'customer order details RPC exists'
);

insert into users (id, telegram_user_id)
values
  ('00000000-0000-0000-0000-000000001701', 1701000001),
  ('00000000-0000-0000-0000-000000001702', 1701000002);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id)
values
  ('00000000-0000-0000-0000-000000001711', '00000000-0000-0000-0000-000000001701', 'BEP20', '0x1701', '0x1701', 'VERIFIED', 'Wallet', 'QR');

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status)
select '00000000-0000-0000-0000-000000001721', 'ORD-1701', '00000000-0000-0000-0000-000000001701', '00000000-0000-0000-0000-000000001711', 'BEP20', id, 'PENDING_PAYMENT'
from payment_methods where code = 'SHAM_CASH';

insert into order_financial_snapshots (internal_order_id, requested_amount, fee_percent, fee_amount, net_usdt_amount, payment_currency, exchange_rate, local_amount, rounding_policy_version, network_config_version)
values ('00000000-0000-0000-0000-000000001721', 100, 10, 10, 0.15, 89.85, 'USD', null, 100, 'test', 1);

select is((select count(*)::integer from get_customer_order_details(1701000001, 'ORD-1701')), 1, 'owner can resolve own order');
select is((select status::text from get_customer_order_details(1701000001, 'ORD-1701') limit 1), 'PENDING_PAYMENT', 'details include current status');
select is((select requested_amount from get_customer_order_details(1701000001, 'ORD-1701') limit 1), 100::numeric, 'details include requested amount');
select is((select local_amount from get_customer_order_details(1701000001, 'ORD-1701') limit 1), 100::numeric, 'details include local amount');
select is((select count(*)::integer from get_customer_order_details(1701000002, 'ORD-1701')), 0, 'another customer cannot resolve the order');
select is((select count(*)::integer from get_customer_order_details(1701000001, 'UNKNOWN')), 0, 'unknown public code returns no order');
select ok(not (select prosecdef from pg_proc where oid = 'public.get_customer_order_details(bigint,text)'::regprocedure), 'RPC is security invoker');
select ok(position('search_path=public' in coalesce((select array_to_string(proconfig, ',') from pg_proc where oid = 'public.get_customer_order_details(bigint,text)'::regprocedure), '')) > 0, 'RPC fixes search path');
select ok(not has_function_privilege('authenticated', 'public.get_customer_order_details(bigint,text)', 'EXECUTE'), 'authenticated callers cannot execute details RPC');

select * from finish();
rollback;
