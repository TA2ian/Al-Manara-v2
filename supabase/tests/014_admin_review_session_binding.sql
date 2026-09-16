begin;

select plan(6);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'transition_order_idempotent'
    order by p.oid desc
    limit 1
)
select ok(
    position('p_session_id uuid' in body) > 0,
    'admin review transition accepts an explicit session id'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'transition_order_idempotent'
    order by p.oid desc
    limit 1
)
select ok(
    position('admin session is required' in body) > 0,
    'admin review requires an explicit session'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'transition_order_idempotent'
    order by p.oid desc
    limit 1
)
select ok(
    position('admin session is invalid or expired' in body) > 0,
    'admin review validates session freshness'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'transition_order_idempotent'
    order by p.oid desc
    limit 1
)
select ok(
    position('admin session is invalid or expired' in body) < position('select oti.result' in body),
    'admin review validates session before idempotency replay'
) from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'transition_order_idempotent'
    order by p.oid desc
    limit 1
)
select ok(
    position("'session_id', p_session_id" in body) > 0,
    'admin review audit metadata binds the session'
) from fn;

select ok(
    not p.prosecdef,
    'admin review transition executes with invoker security context'
)
from pg_proc p
where p.proname = 'transition_order_idempotent'
order by p.oid desc
limit 1;

select * from finish();
rollback;
