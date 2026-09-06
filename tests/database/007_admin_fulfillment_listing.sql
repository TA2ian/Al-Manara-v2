begin;

select plan(3);

select ok(
    to_regprocedure('list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)') is not null,
    'claim-aware fulfillment listing RPC exists'
);

select ok(
    position('fulfillment_claimed_by' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_fulfillment_orders'
        limit 1
    ))) > 0,
    'fulfillment listing exposes claim ownership'
);

select ok(
    position('order_fulfillment_claims' in pg_get_functiondef((
        select p.oid
        from pg_proc p
        where p.proname = 'list_admin_fulfillment_orders'
        limit 1
    ))) > 0,
    'fulfillment listing reads authoritative claim ownership'
);

select * from finish();
rollback;
