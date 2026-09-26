-- Resolve the authenticated administrator's actor type from the database.
-- Telegram callback/message data never supplies or selects actor_type.
create or replace function resolve_admin_actor_type(
    p_telegram_user_id bigint
)
returns table (actor_type admin_actor_type)
language sql
security invoker
set search_path = public
as $$
    select au.actor_type
      from admin_users au
     where au.telegram_user_id = p_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     limit 1;
$$;

revoke all on function resolve_admin_actor_type(bigint) from public;
grant execute on function resolve_admin_actor_type(bigint) to service_role;
