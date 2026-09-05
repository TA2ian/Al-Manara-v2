begin;

select plan(1);

select ok(
    position('PENDING_PAYMENT' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'create_purchase_order_atomic'
        limit 1
    ))) > 0,
    'atomic purchase-order creation enters the canonical PENDING_PAYMENT state'
);

select * from finish();
rollback;
