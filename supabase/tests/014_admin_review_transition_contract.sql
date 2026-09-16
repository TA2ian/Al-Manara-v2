begin;

select plan(4);

select ok(
    not p.prosecdef,
    'admin review transition executes with invoker security context'
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname = 'admin_review_order_transition_idempotent'
limit 1;

select ok(
    has_function_privilege('public', 'admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid)', 'EXECUTE') = false,
    'public cannot execute admin review transition'
);

select ok(
    has_function_privilege('service_role', 'admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid)', 'EXECUTE'),
    'service_role can execute admin review transition'
);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'admin_review_order_transition_idempotent'
    limit 1
)
select ok(
    position('revoked_at is null' in body) > 0
    and position('expires_at > now()' in body) > 0
    and position('actor_type = p_actor_type' in body) > 0,
    'admin review transition binds an active session to the resolved actor type'
) from fn;

select * from finish();
rollback;
