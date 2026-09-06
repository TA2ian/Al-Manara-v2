begin;

select plan(3);

select ok(
    position('fulfillment_claimed_by' in pg_get_function_result((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        limit 1
    ))) > 0,
    'admin order listing exposes fulfillment claim ownership'
);

select ok(
    position('order_fulfillment_claims' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        limit 1
    ))) > 0,
    'admin order listing reads the authoritative fulfillment claim table'
);

select ok(
    position('fulfillment' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        limit 1
    ))) > 0,
    'admin order listing retains the fulfillment list type'
);

select * from finish();
rollback;
