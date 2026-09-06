begin;

select plan(3);

select ok(
    position('fulfillment_claimed_by bigint' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
          and p.prokind = 'f'
        order by p.oid desc
        limit 1
    ))) > 0,
    'admin order listing exposes the fulfillment claim owner'
);

select ok(
    position('order_fulfillment_claims' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
          and p.prokind = 'f'
        order by p.oid desc
        limit 1
    ))) > 0,
    'admin order listing reads active fulfillment claims'
);

select ok(
    position("status = 'APPROVED'" in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_orders'
          and p.prokind = 'f'
        order by p.oid desc
        limit 1
    ))) > 0,
    'fulfillment listing remains restricted to approved orders'
);

select * from finish();
rollback;
