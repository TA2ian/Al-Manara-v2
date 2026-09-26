begin;

select plan(3);

select ok(
    to_regprocedure('list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)') is not null,
    'claim-aware fulfillment listing RPC exists'
);

select ok(
    not has_function_privilege(
        'anon',
        'public.list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)',
        'execute'
    ),
    'fulfillment listing RPC is not publicly executable'
);

select ok(
    has_function_privilege(
        'service_role',
        'public.list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)',
        'execute'
    ),
    'backend service role can execute fulfillment listing RPC'
);

select * from finish();
rollback;
