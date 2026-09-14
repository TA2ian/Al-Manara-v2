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
    position('revoke execute on function close_order_without_fulfillment' in pg_get_functiondef((
        select p.oid from pg_proc p
        where p.proname = 'close_order_without_fulfillment'
        limit 1
    ))) = 0,
    'function body does not contain privilege mutation statements'
);

select * from finish();
rollback;
