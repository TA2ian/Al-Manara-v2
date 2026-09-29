begin;

select plan(4);

select has_function(
    'public',
    'resolve_admin_actor_type',
    array['bigint'],
    'authoritative admin actor resolution RPC exists'
);

select ok(
    not p.prosecdef,
    'actor resolution executes with invoker security context'
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname = 'resolve_admin_actor_type'
limit 1;

select ok(
    has_function_privilege('public', 'resolve_admin_actor_type(bigint)', 'EXECUTE') = false,
    'actor resolution is not executable by PUBLIC'
);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'resolve_admin_actor_type'
    limit 1
)
select ok(
    position('au.enabled' in body) > 0
    and position('(au.actor_type = ''primary'' or au.emergency_only)' in body) > 0,
    'actor resolution enforces enabled and emergency-only backup eligibility'
) from fn;

select * from finish();
rollback;
