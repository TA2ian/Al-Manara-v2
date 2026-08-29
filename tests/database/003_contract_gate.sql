begin;

select plan(2);

select ok(
  (select count(*) from pg_proc where proname = 'reserve_receipt_submission') = 1,
  'canonical receipt reservation RPC exists'
);

select ok(
  (select count(*) from pg_proc where proname = 'finalize_receipt_submission') = 1,
  'canonical receipt finalization RPC exists'
);

select * from finish();
rollback;
