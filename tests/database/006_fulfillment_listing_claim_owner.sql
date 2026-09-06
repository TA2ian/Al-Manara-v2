begin;

select plan(2);

select ok(
    position('fulfillment_claimed_by bigint' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        order by p.oid desc
        limit 1
    ))) > 0,
    'admin order listing exposes the fulfillment claim owner'
);

select ok(
    position('left join order_fulfillment_claims fc' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
        order by p.oid desc
        limit 1
    ))) > 0,
    'admin order listing reads active fulfillment claims'
);

select * from finish();
rollback;
