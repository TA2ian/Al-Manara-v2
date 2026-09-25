begin;

select plan(12);

select ok(
  to_regprocedure('public.admin_reopen_order_for_receipt(uuid,bigint,bigint,admin_actor_type,uuid,uuid,text,text,text)') is not null,
  'order reopen RPC exists'
);

select ok(
  has_function_privilege(
    'anon',
    'public.admin_reopen_order_for_receipt(uuid,bigint,bigint,admin_actor_type,uuid,uuid,text,text,text)',
    'EXECUTE'
  ) = false,
  'order reopen is not executable by anon'
);

insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values (23001001, 'primary', true, false);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000002301', 23002001);

insert into wallets (
  id,user_id,network_code,address,normalized_address,status,label,qr_image_file_id
) values (
  '00000000-0000-0000-0000-000000002311',
  '00000000-0000-0000-0000-000000002301',
  'BEP20',
  '0x0000000000000000000000000000000000002301',
  '0x0000000000000000000000000000000000002301',
  'VERIFIED',
  'reopen test',
  'QR-2301'
);

insert into orders (
  internal_order_id,public_order_code,user_id,wallet_id,network_code,payment_method_id,status,version
)
select
  '00000000-0000-0000-0000-000000002321','ORD-2301',
  '00000000-0000-0000-0000-000000002301',
  '00000000-0000-0000-0000-000000002311',
  'BEP20',id,'CLARIFICATION_REQUIRED',5
from payment_methods where code='SHAM_CASH';

insert into admin_sessions (id,admin_telegram_user_id,expires_at)
values ('00000000-0000-0000-0000-000000002331',23001001,now()+interval '10 minutes');

select * into temporary test_023_reopen_confirmation
from create_admin_action_confirmation(
  23001001,'primary','00000000-0000-0000-0000-000000002331',
  'order.reopen_receipt',repeat('c',64)
);

select * into temporary test_023_wrong_operation_confirmation
from create_admin_action_confirmation(
  23001001,'primary','00000000-0000-0000-0000-000000002331',
  'fulfillment.complete',repeat('e',64)
);

select * into temporary test_023_tamper_confirmation
from create_admin_action_confirmation(
  23001001,'primary','00000000-0000-0000-0000-000000002331',
  'order.reopen_receipt',repeat('f',64)
);

select lives_ok($$
  select * from admin_reopen_order_for_receipt(
    '00000000-0000-0000-0000-000000002321',5,23001001,'primary',
    '00000000-0000-0000-0000-000000002331',
    (select confirmation_id from test_023_reopen_confirmation),
    repeat('c',64),'customer corrected receipt','recover-2301'
  )
$$,'valid clarification reopen succeeds');

select is(
  (select status::text from orders where internal_order_id='00000000-0000-0000-0000-000000002321'),
  'PENDING_PAYMENT','reopen returns order to human review'
);

select is(
  (select version from orders where internal_order_id='00000000-0000-0000-0000-000000002321'),
  6::bigint,'reopen increments version exactly once'
);

select is(
  (select count(*)::integer from audit_logs
   where target_id='00000000-0000-0000-0000-000000002321'
     and action='order.recovered_to_review'),
  1,'reopen is audited once'
);

select throws_ok($$
  select * from admin_reopen_order_for_receipt(
    '00000000-0000-0000-0000-000000002321',6,23001001,'primary',
    '00000000-0000-0000-0000-000000002331',
    (select confirmation_id from test_023_reopen_confirmation),
    repeat('c',64),'second reopen','recover-2303'
  )
$$,'admin action confirmation is invalid, expired, or already consumed','a consumed confirmation cannot authorize a second mutation');

select throws_ok($
  select * from admin_reopen_order_for_receipt(
    '00000000-0000-0000-0000-000000002321',6,23001001,'primary',
    '00000000-0000-0000-0000-000000002331',
    gen_random_uuid(),repeat('d',64),'wrong state','recover-2302'
  )
$,'admin action confirmation is invalid, expired, or already consumed','a fabricated confirmation cannot authorize reopen');

select throws_ok($
  select * from admin_reopen_order_for_receipt(
    '00000000-0000-0000-0000-000000002321',6,23001001,'primary',
    '00000000-0000-0000-0000-000000002331',
    (select confirmation_id from test_023_wrong_operation_confirmation),
    repeat('e',64),'wrong operation','recover-2304'
  )
$,'admin action confirmation is invalid, expired, or already consumed','a fulfillment confirmation cannot authorize receipt reopen');

select throws_ok($
  select * from admin_reopen_order_for_receipt(
    '00000000-0000-0000-0000-000000002321',6,23001001,'primary',
    '00000000-0000-0000-0000-000000002331',
    (select confirmation_id from test_023_tamper_confirmation),
    repeat('a',64),'tampered fingerprint','recover-2305'
  )
$,'admin action confirmation is invalid, expired, or already consumed','a mismatched fingerprint cannot authorize receipt reopen');

select ok(
  exists(
    select 1 from order_transition_idempotency
    where idempotency_key='recover-2301'
      and (result->>'operation')='order.reopen_receipt'
  ),
  'reopen idempotency result is persisted'
);

select * from finish();
rollback;
