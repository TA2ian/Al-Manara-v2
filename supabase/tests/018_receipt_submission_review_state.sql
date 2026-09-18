begin;

select plan(13);

select ok(
  to_regprocedure('public.finalize_receipt_submission(uuid,text,text,text)') is not null,
  'receipt finalization RPC exists'
);

select ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.receipt_submissions'::regclass
      and conname = 'receipt_processing_status_valid'
  ),
  'receipt processing status constraint exists'
);

select ok(
  (select pg_get_constraintdef(oid)
     from pg_constraint
    where conrelid = 'public.receipt_submissions'::regclass
      and conname = 'receipt_processing_status_valid')
    like '%SUBMITTED%',
  'SUBMITTED receipt state is allowed'
);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000001801', 1801000001);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id)
values (
  '00000000-0000-0000-0000-000000001811',
  '00000000-0000-0000-0000-000000001801',
  'BEP20',
  '0x0000000000000000000000000000000000001801',
  '0x0000000000000000000000000000000000001801',
  'VERIFIED',
  'Receipt Test Wallet',
  'QR-1801'
);

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status)
select
  '00000000-0000-0000-0000-000000001821',
  'ORD-1801',
  '00000000-0000-0000-0000-000000001801',
  '00000000-0000-0000-0000-000000001811',
  'BEP20',
  id,
  'PENDING_PAYMENT'
from payment_methods where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, exchange_rate,
  local_amount, rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000001821',
  100, 10, 10, 0.15, 89.85, 'USD', null, 100, 'test', 1
);

select lives_ok($$
  select * from reserve_receipt_submission(
    '00000000-0000-0000-0000-000000001821',
    1801000001,
    'receipt-contract-1801',
    'IMAGE',
    null,
    'telegram-file-1801',
    'image/png',
    now()
  )
$$, 'customer receipt can be reserved');

select lives_ok($$
  select * from finalize_receipt_submission(
    (select id from receipt_submissions where idempotency_key = 'receipt-contract-1801'),
    'SUBMITTED'
  )
$$, 'customer receipt can be queued for review');

select is(
  (select processing_status from receipt_submissions where idempotency_key = 'receipt-contract-1801'),
  'SUBMITTED',
  'receipt remains submitted after queueing'
);

select is(
  (select status::text from orders where internal_order_id = '00000000-0000-0000-0000-000000001821'),
  'UNDER_REVIEW',
  'customer receipt moves order into human review'
);

select is(
  (select version from orders where internal_order_id = '00000000-0000-0000-0000-000000001821'),
  3::bigint,
  'receipt queue transition increments order version twice'
);

select throws_ok($$
  select * from finalize_receipt_submission(
    (select id from receipt_submissions where idempotency_key = 'receipt-contract-1801'),
    'SUCCEEDED'
  )
$$, 'P0001', 'receipt submission is not processing', 'a submitted receipt cannot be finalized twice');

select is(
  (select count(*)::integer from audit_logs
    where target_id = '00000000-0000-0000-0000-000000001821'
      and action in ('order.receipt_submitted','order.receipt_queued_for_review')),
  2,
  'receipt queue creates both audit events'
);

select ok(
  not exists (
    select 1 from orders
    where internal_order_id = '00000000-0000-0000-0000-000000001821'
      and status = 'APPROVED'
  ),
  'receipt submission never auto-approves the order'
);

select lives_ok($$
  select * from get_customer_order_details(1801000001, 'ORD-1801')
$$, 'customer can still resolve the order after submission');

select is(
  (select status::text from get_customer_order_details(1801000001, 'ORD-1801') limit 1),
  'UNDER_REVIEW',
  'customer details expose human review state'
);

select * from finish();
rollback;
