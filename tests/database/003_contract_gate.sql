begin;

select plan(5);

select ok(
  (select count(*) from pg_proc where proname = 'reserve_receipt_submission') = 1,
  'canonical receipt reservation RPC exists'
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

select * from finish();
rollback;
