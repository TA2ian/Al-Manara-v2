begin;

select plan(4);

select ok(
    position('fulfillment_claimed_by bigint' in pg_get_functiondef((
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
    position('o.status = ''APPROVED''' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        limit 1
    ))) > 0,
    'fulfillment list remains restricted to approved orders'
);

select ok(
    exists (
        select 1
        from pg_proc p
        where p.proname = 'list_admin_orders'
          and pg_get_function_result(p.oid) like '%fulfillment_claimed_by%'
    ),
    'list_admin_orders return contract includes claim ownership'
);

select * from finish();
rollback;
