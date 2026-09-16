begin;

select plan(5);

select ok(
    not p.prosecdef,
    'admin session validation executes with invoker security context'
)
from pg_proc p
where p.proname = 'validate_admin_session'
limit 1;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'validate_admin_session'
    limit 1
)
select ok(position('s.revoked_at is null' in body) > 0, 'validation rejects revoked sessions') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'validate_admin_session'
    limit 1
)
select ok(position('s.expires_at > now()' in body) > 0, 'validation requires an unexpired session') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'validate_admin_session'
    limit 1
)
select ok(position('s.admin_telegram_user_id = p_admin_telegram_user_id' in body) > 0, 'validation binds the session to the authenticated admin') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'validate_admin_session'
    limit 1
)
select ok(position('au.actor_type = p_actor_type' in body) > 0, 'validation binds the session to the resolved actor type') from fn;

select * from finish();
rollback;
