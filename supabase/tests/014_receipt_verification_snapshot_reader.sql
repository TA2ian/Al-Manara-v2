begin;

select plan(7);

select ok(
    not p.prosecdef,
    'receipt snapshot reader executes with invoker security context'
)
from pg_proc p
where p.proname = 'get_receipt_verification_snapshot'
limit 1;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'get_receipt_verification_snapshot'
    limit 1
)
select ok(position('order_financial_snapshots' in body) > 0, 'reader uses the authoritative financial snapshot') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'get_receipt_verification_snapshot'
    limit 1
)
select ok(position('s.local_amount' in body) > 0, 'local_amount is the expected payment amount') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'get_receipt_verification_snapshot'
    limit 1
)
select ok(position('s.exchange_rate' in body) > 0, 'exchange rate comes from the snapshot') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'get_receipt_verification_snapshot'
    limit 1
)
select ok(position('w.address' in body) > 0, 'wallet address is linked to the authoritative order wallet') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'get_receipt_verification_snapshot'
    limit 1
)
select ok(position('st.absolute_tolerance' in body) > 0, 'verification tolerance comes from persisted settings') from fn;

select ok(
    has_function_privilege('public', 'get_receipt_verification_snapshot(uuid)', 'EXECUTE') = false,
    'snapshot reader is not executable by public'
);

select * from finish();
rollback;
