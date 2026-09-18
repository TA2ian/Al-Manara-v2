begin;

select plan(9);

select ok(
  to_regprocedure('public.get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid)') is not null,
  'admin review details RPC exists'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid)',
    'EXECUTE'
  ),
  'only service_role executes review details RPC'
);

select ok(
  not has_function_privilege(
    'anon',
    'public.get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid)',
    'EXECUTE'
  ),
  'anon cannot execute review details RPC'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.get_admin_order_review_details(bigint,admin_actor_type,uuid,uuid)',
    'EXECUTE'
  ),
  'authenticated cannot execute review details RPC'
);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000001901', 1901000001);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id)
values (
  '00000000-0000-0000-0000-000000001911',
  '00000000-0000-0000-0000-000000001901',
  'BEP20',
  '0x0000000000000000000000000000000000001901',
  '0x0000000000000000000000000000000000001901',
  'VERIFIED',
  'Admin Review Detail Test',
  'QR-1901'
);

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status)
select
  '00000000-0000-0000-0000-000000001921',
  'ORD-1901',
  '00000000-0000-0000-0000-000000001901',
  '00000000-0000-0000-0000-000000001911',
  'BEP20',
  (select id from payment_methods where code = 'SHAM_CASH' limit 1),
  'UNDER_REVIEW'
where exists (select 1 from payment_methods where code = 'SHAM_CASH');

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, exchange_rate,
  local_amount, rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000001921',
  100, 10, 10, 0.15, 89.85, 'USD', null, 100, 'test', 1
);

insert into receipt_submissions (
  id, internal_order_id, source, attempt_number, idempotency_key,
  input_type, telegram_file_id, mime_type, submitted_at,
  linkage_status, processing_status
) values (
  '00000000-0000-0000-0000-000000001931',
  '00000000-0000-0000-0000-000000001921',
  'customer', 1, 'admin-review-detail-1901',
  'IMAGE', 'telegram-receipt-1901', 'image/png', now(),
  'PENDING', 'SUBMITTED'
);

-- Tests need a configured admin actor. The fixture uses the primary admin
-- seeded by the base schema when present.
select ok(
  exists (
    select 1 from admin_users where enabled and actor_type = 'primary'
  ) or exists (
    select 1 from admin_users where enabled and emergency_only
  ),
  'an enabled review actor exists in the test fixture'
);

select is(
  (select count(*)::integer
     from get_admin_order_review_details(
       (select telegram_user_id from admin_users where enabled limit 1),
       (select actor_type from admin_users where enabled limit 1),
       '00000000-0000-0000-0000-000000001921',
       (select id from admin_sessions where revoked_at is null and expires_at > now() limit 1)
     )
  ),
  1,
  'authorized fresh session can read one review detail'
);

select is(
  (select local_amount from get_admin_order_review_details(
    (select telegram_user_id from admin_users where enabled limit 1),
    (select actor_type from admin_users where enabled limit 1),
    '00000000-0000-0000-0000-000000001921',
    (select id from admin_sessions where revoked_at is null and expires_at > now() limit 1)
  ) limit 1),
  100::numeric,
  'review details expose authoritative local amount'
);

select is(
  (select receipt_telegram_file_id from get_admin_order_review_details(
    (select telegram_user_id from admin_users where enabled limit 1),
    (select actor_type from admin_users where enabled limit 1),
    '00000000-0000-0000-0000-000000001921',
    (select id from admin_sessions where revoked_at is null and expires_at > now() limit 1)
  ) limit 1),
  'telegram-receipt-1901',
  'review details expose the customer receipt file id'
);

select is(
  (select status::text from get_admin_order_review_details(
    (select telegram_user_id from admin_users where enabled limit 1),
    (select actor_type from admin_users where enabled limit 1),
    '00000000-0000-0000-0000-000000001921',
    (select id from admin_sessions where revoked_at is null and expires_at > now() limit 1)
  ) limit 1),
  'UNDER_REVIEW',
  'review details expose the current order state'
);

select * from finish();
rollback;
