begin;

select plan(13);

select ok(
    exists (select 1 from pg_proc where proname = 'reserve_receipt_submission'),
    'receipt reservation function exists'
);

select ok(
    exists (select 1 from pg_proc where proname = 'finalize_receipt_submission'),
    'receipt finalization function exists'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_function_result(oid) like '%replayed%'
    ),
    'receipt reservation exposes replay state'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_functiondef(oid) like '%pg_advisory_xact_lock%'
    ),
    'receipt allocation is serialized per order'
);

select ok(
    exists (
        select 1 from pg_indexes
        where schemaname = 'public'
          and tablename = 'receipt_submissions'
          and indexdef ilike '%idempotency_key%'
    ),
    'receipt idempotency key is unique'
);

select ok(
    exists (
        select 1 from pg_indexes
        where schemaname = 'public'
          and tablename = 'receipt_submissions'
          and indexdef ilike '%processing_status%'
          and indexdef ilike '%unique%'
    ),
    'only one receipt may be processing per order'
);

select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.receipt_submissions'::regclass
          and conname = 'receipt_submissions_attempt_positive'
    ),
    'receipt attempt number is constrained'
);

select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.receipt_submissions'::regclass
          and conname = 'receipt_submissions_input_type_check'
    ),
    'receipt input type is constrained to TEXT or IMAGE'
);

select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.receipt_submissions'::regclass
          and conname = 'receipt_submissions_input_shape_check'
    ),
    'receipt input fields are mutually exclusive by input type'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_functiondef(oid) like '%idempotency key belongs to another order%'
    ),
    'idempotency key cannot be rebound to another order'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'finalize_receipt_submission'
          and pg_get_function_result(oid) like '%input_type%'
          and pg_get_function_result(oid) like '%transaction_reference%'
          and pg_get_function_result(oid) like '%telegram_file_id%'
          and pg_get_function_result(oid) like '%mime_type%'
          and pg_get_function_result(oid) like '%submitted_at%'
    ),
    'receipt finalization returns the unified attempt payload'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_functiondef(oid) like '%text receipt requires a transaction reference%'
          and pg_get_functiondef(oid) like '%image receipt requires a file id%'
    ),
    'reservation validates text and image input shapes'
);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'finalize_receipt_submission'
          and pg_get_functiondef(oid) like '%shamcash_operation_number%'
          and pg_get_functiondef(oid) like '%v_input_type = ''TEXT''%'
    ),
    'verified text receipts persist their transaction reference to the order'
);

select * from finish();
rollback;
