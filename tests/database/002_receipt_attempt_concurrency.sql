begin;

select plan(2);

select ok(
  exists (
    select 1
    from pg_proc
    where proname = 'enforce_receipt_attempt_limit'
      and prosrc like '%pg_advisory_xact_lock%'
  ),
  'receipt attempt allocation is serialized per order'
);

select ok(
  exists (
    select 1
    from pg_trigger
    where tgname = 'receipt_submissions_attempt_limit'
      and tgrelid = 'public.receipt_submissions'::regclass
  ),
  'receipt attempt allocation is enforced by a database trigger'
);

select * from finish();
rollback;
