begin;

select plan(4);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'close_order_without_fulfillment'
    limit 1
)
select ok(
    position('admin session is required' in body) > 0,
    'closure requires an explicit session'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'close_order_without_fulfillment'
    limit 1
)
select ok(
    position('admin session is invalid or expired' in body) > 0,
    'closure validates session freshness'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'close_order_without_fulfillment'
    limit 1
)
select ok(
    position('admin session is invalid or expired' in body) < position('select ik.response_json' in body),
    'closure validates session before reading an idempotency replay'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'close_order_without_fulfillment'
    limit 1
)
select ok(
    lower(body) like '%security invoker%',
    'closure executes with invoker security context'
) from fn;

select * from finish();
rollback;
