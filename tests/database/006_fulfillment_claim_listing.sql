begin;

select plan(3);

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
    'admin order listing joins the active fulfillment claim'
);

select ok(
    position("fulfillment_claimed_by" in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        limit 1
    ))) > 0,
    'claim ownership is part of the authoritative listing contract'
);

select * from finish();
rollback;
