begin;

select plan(23);

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
  position('PAYMENT_SUBMITTED' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'finalize_receipt_submission' limit 1))) > 0,
  'successful receipt finalization advances the order to PAYMENT_SUBMITTED'
);

select ok(
  position('UNDER_REVIEW' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'finalize_receipt_submission' limit 1))) > 0,
  'successful receipt finalization enters the human review queue'
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

select ok(
  position("v_current_status = 'APPROVED' and p_target_status = 'COMPLETED'" in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'transition_order_if_version' limit 1))) = 0,
  'generic order transition cannot complete approved orders'
);

select ok(
  (select count(*) from pg_proc where proname = 'get_order_for_transition') = 1,
  'order transition read RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'authorize_admin_order_review') = 1,
  'admin order review authorization RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'transition_order_idempotent') = 1,
  'atomic idempotent admin transition RPC exists'
);

select ok(
  position('on conflict (idempotency_key) do nothing' in lower(pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'transition_order_idempotent' limit 1)))) > 0,
  'atomic transition reserves idempotency keys safely under concurrency'
);

select ok(
  to_regclass('public.order_transition_idempotency') is not null,
  'order transition idempotency table exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'claim_order_fulfillment') = 1,
  'atomic fulfillment claim RPC exists'
);

select ok(
  position('APPROVED' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0,
  'fulfillment claim is restricted to APPROVED orders'
);

select ok(
  position('order_fulfillment_claims' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0,
  'fulfillment claim persists an active claim'
);

select ok(
  (select count(*) from pg_proc where proname = 'complete_order_fulfillment') = 1,
  'atomic fulfillment completion RPC exists'
);

select ok(
  position('active fulfillment claim is required' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0,
  'fulfillment completion requires an active claim'
);

select ok(
  to_regclass('public.order_fulfillment_idempotency') is not null,
  'fulfillment idempotency table exists'
);

select ok(
  to_regclass('public.orders_fulfillment_completion_guard') is not null,
  'database completion guard trigger exists'
);

select * from finish();
rollback;
