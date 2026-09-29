-- Normalize the audit actor contract at the database boundary.
-- Older privileged RPCs were written before actor_kind was introduced and
-- provide actor_telegram_user_id + actor_type but no actor_kind. Derive the
-- missing value centrally while rejecting contradictory explicit values.
create or replace function set_audit_actor_kind()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_expected_kind text;
begin
    if new.actor_telegram_user_id is null then
        if new.actor_type is not null or new.actor_kind is not null then
            raise exception 'system audit event cannot carry an actor type or actor kind';
        end if;
        return new;
    end if;

    if new.actor_type is not null then
        v_expected_kind := 'admin';
    else
        v_expected_kind := 'customer';
    end if;

    if new.actor_kind is null then
        new.actor_kind := v_expected_kind;
    elsif new.actor_kind <> v_expected_kind then
        raise exception 'audit actor kind does not match actor fields';
    end if;

    return new;
end;
$$;

drop trigger if exists audit_logs_actor_kind_normalize on audit_logs;

create trigger audit_logs_actor_kind_normalize
before insert on audit_logs
for each row
execute function set_audit_actor_kind();

revoke all on function set_audit_actor_kind() from public, anon, authenticated;
