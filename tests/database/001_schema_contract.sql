begin;

select plan(12);

select is(
  (select count(*)::integer from information_schema.tables where table_schema = 'public' and table_name in (
    'users', 'network_configs', 'wallets', 'wallet_verifications', 'payment_methods',
    'admin_payment_accounts', 'exchange_rates', 'settings', 'orders', 'order_financial_snapshots',
    'receipt_submissions', 'receipt_evidence', 'receipt_verification_results', 'admin_users',
    'admin_totp_credentials', 'admin_step_up_confirmations', 'audit_logs'
  )),
  17,
  'all required persistence tables exist'
);

select is(
  (select count(*)::integer from network_configs where enabled),
  2,
  'exactly two networks are enabled at launch'
);

select is(
  (select string_agg(code::text, ',' order by code) from network_configs where enabled),
  'BEP20,TRC20',
  'only BEP20 and TRC20 are enabled at launch'
);

select is(
  (select count(*)::integer from network_configs where code in ('TON','ARB','ETH','SOL') and not enabled),
  4,
  'deferred networks remain disabled'
);

select ok(
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and tablename = 'orders' and indexname = 'orders_shamcash_operation_number_uq'
  ),
  'ShamCash operation number has a unique index'
);

select ok(
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and tablename = 'orders' and indexname = 'orders_review_queue_idx'
  ),
  'order review queue has a dedicated index'
);

select ok(
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and tablename = 'admin_payment_accounts' and indexname = 'admin_payment_accounts_method_currency_uq'
  ),
  'admin payment accounts are unique per payment method and currency'
);

select ok(
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and tablename = 'exchange_rates' and indexname = 'exchange_rates_active_pair_uq'
  ),
  'only one active exchange rate is allowed per currency pair'
);

select ok(
  exists (
    select 1 from pg_trigger
    where tgname = 'orders_status_version_guard'
      and tgrelid = 'public.orders'::regclass
  ),
  'order status updates are guarded by optimistic versioning'
);

select ok(
  exists (
    select 1 from pg_trigger
    where tgname = 'order_financial_snapshots_no_update'
      and tgrelid = 'public.order_financial_snapshots'::regclass
  ),
  'financial snapshots are immutable'
);

select ok(
  exists (
    select 1 from pg_trigger
    where tgname = 'audit_logs_no_update_delete'
      and tgrelid = 'public.audit_logs'::regclass
  ),
  'audit logs are append-only'
);

select is(
  (select max_file_size_bytes from settings where id = true),
  5242880::bigint,
  'default file limit is 5 MiB'
);

select * from finish();
rollback;
