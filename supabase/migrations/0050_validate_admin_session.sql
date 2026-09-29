-- Validate an explicit, recent administrative session.
-- The caller must prove ownership, actor type, non-revocation and expiry.
create or replace function validate_admin_session(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_admin_telegram_user_id <= 0 then
        raise exception 'admin telegram user id must be positive';
    end if;
    if p_actor_type is null then
        raise exception 'admin actor type is required';
    end if;
    if p_session_id is null then
        raise exception 'admin session id is required';
    end if;

    return exists (
        select 1
          from admin_sessions s
          join admin_users au
            on au.telegram_user_id = s.admin_telegram_user_id
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_admin_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
           and au.enabled
           and au.actor_type = p_actor_type
           and (au.actor_type = 'primary' or au.emergency_only)
    );
end;
$$;

revoke all on function validate_admin_session(bigint, admin_actor_type, uuid) from public;
grant execute on function validate_admin_session(bigint, admin_actor_type, uuid) to service_role;
