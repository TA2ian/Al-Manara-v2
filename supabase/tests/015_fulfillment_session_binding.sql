begin;

select plan(8);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'claim_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('admin session is required' in body) > 0, 'claim requires an explicit session') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'claim_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('admin session is invalid or expired' in body) > 0, 'claim validates session freshness') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'claim_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('session_id' in body) > 0, 'claim audit records the session') from fn;

select ok(
    not p.prosecdef,
    'claim session-bound overload uses invoker security'
)
from pg_proc p
where p.proname = 'claim_order_fulfillment'
  and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
limit 1;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'complete_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('admin session is required' in body) > 0, 'completion requires an explicit session') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'complete_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('admin session is invalid or expired' in body) > 0, 'completion validates session freshness') from fn;

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    where p.proname = 'complete_order_fulfillment'
      and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
    limit 1
)
select ok(position('session_id' in body) > 0, 'completion audit records the session') from fn;

select ok(
    not p.prosecdef,
    'completion session-bound overload uses invoker security'
)
from pg_proc p
where p.proname = 'complete_order_fulfillment'
  and pg_get_function_arguments(p.oid) like '%p_session_id uuid%'
limit 1;

select * from finish();
rollback;
