begin;

select plan(5);

select ok(
    to_regprocedure('public.resolve_admin_actor_type(bigint)') is not null,
    'authoritative admin actor resolver exists'
);

select ok(
    has_function_privilege('public', 'resolve_admin_actor_type(bigint)', 'EXECUTE') = false
    and has_function_privilege('service_role', 'resolve_admin_actor_type(bigint)', 'EXECUTE'),
    'actor resolver is service-role-only'
);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'close_order_without_fulfillment'
      and pg_get_function_identity_arguments(p.oid) = 'p_order_id uuid, p_expected_version bigint, p_admin_telegram_user_id bigint, p_session_id uuid, p_reason text, p_idempotency_key text'
    limit 1
)
select ok(
    position('select au.actor_type into v_actor_type' in body) > 0
    and position('au.enabled' in body) > 0
    and position('(au.actor_type = ''primary'' or au.emergency_only)' in body) > 0,
    'closure resolves the actor from the authoritative admin record'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'close_order_without_fulfillment'
      and pg_get_function_identity_arguments(p.oid) = 'p_order_id uuid, p_expected_version bigint, p_admin_telegram_user_id bigint, p_session_id uuid, p_reason text, p_idempotency_key text'
    limit 1
)
select ok(
    position('select au.actor_type into v_actor_type' in body) < position('select ik.response_json' in body),
    'closure resolves actor before reading an idempotency replay'
) from fn;

select ok(
    not p.prosecdef,
    'closure executes with invoker security context'
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname = 'close_order_without_fulfillment'
limit 1;

select * from finish();
rollback;
