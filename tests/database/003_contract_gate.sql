begin;

select plan(8);

select ok(
  (select count(*) from pg_proc where proname = 'reserve_receipt_submission') = 1,
  'canonical receipt reservation RPC exists'
);

select ok(
  exists (
    select 1
      from pg_proc p
      where p.proname = 'reserve_receipt_submission'
        and p.proargtypes::oid[] = array[
          'uuid'::regtype,
          'bigint'::regtype,
          'text'::regtype,
          'text'::regtype,
          'text'::regtype,
          'timestamptz'::regtype
        ]
  ),
  'receipt reservation RPC requires Telegram identity'
);

select ok(
  (select count(*) from pg_proc where proname = 'finalize_receipt_submission') = 1,
  'canonical receipt finalization RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'list_verified_wallets_for_telegram_user') = 1,
  'verified wallet listing RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'register_pending_wallet_for_telegram_user') = 1,
  'pending wallet registration RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'disable_wallet_for_telegram_user') = 1,
  'wallet disable RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'transition_order_if_version') = 1,
  'canonical order transition RPC exists'
);

select ok(
  position('from admin_users au' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'transition_order_if_version' limit 1))) > 0,
  'order transition RPC verifies supplied admin actors against admin_users'
);

select * from finish();
rollback;
