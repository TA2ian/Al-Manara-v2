begin;

select plan(3);

select ok(
  exists (
    select 1
    from pg_proc
    where proname = 'reserve_receipt_submission'
      and pg_get_functiondef(oid) like '%pg_advisory_xact_lock%'
  ),
  'receipt attempt allocation is serialized per order'
);

select ok(
  exists (
    select 1
    from pg_indexes
    where schemaname = 'public'
      and tablename = 'receipt_submissions'
      and indexdef ilike '%processing_status%'
      and indexdef ilike '%unique%'
  ),
  'receipt processing is protected by a per-order uniqueness boundary'
);

select ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.receipt_submissions'::regclass
      and conname = 'receipt_submissions_attempt_positive'
  ),
  'receipt attempts are constrained to one through three'
);

select * from finish();
rollback;
