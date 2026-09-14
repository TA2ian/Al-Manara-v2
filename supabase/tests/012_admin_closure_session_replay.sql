begin;

select plan(4);

select ok(
    position('admin session is required' in pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    ))) > 0,
    'closure requires an explicit session'
);

select ok(
    position('admin session is invalid or expired' in pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    ))) > 0,
    'closure validates session freshness'
);

select ok(
    position('admin session is invalid or expired' in pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    ))) < position('select ik.response_json' in pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    )),
    'closure validates session before reading an idempotency replay'
);

select ok(
    lower(pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    ))) like '%security invoker%',
    'closure executes with invoker security context'
);

select * from finish();
rollback;
