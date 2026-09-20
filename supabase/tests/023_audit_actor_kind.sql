-- Audit actor contract: admin and customer identities are represented distinctly.
do $$
declare
  admin_id bigint := 910000001;
  customer_id bigint := 910000002;
begin
  insert into audit_logs (
    actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id
  ) values (
    admin_id, 'admin', 'primary', 'test_admin_actor', 'test', 'admin'
  );

  insert into audit_logs (
    actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id
  ) values (
    customer_id, 'customer', null, 'test_customer_actor', 'test', 'customer'
  );

  if not exists (
    select 1 from audit_logs
    where actor_telegram_user_id=admin_id
      and actor_kind='admin'
      and actor_type='primary'
  ) then
    raise exception 'admin audit actor contract failed';
  end if;

  if not exists (
    select 1 from audit_logs
    where actor_telegram_user_id=customer_id
      and actor_kind='customer'
      and actor_type is null
  ) then
    raise exception 'customer audit actor contract failed';
  end if;

  begin
    insert into audit_logs (
      actor_telegram_user_id, actor_kind, actor_type, action, target_type
    ) values (customer_id + 1, 'customer', 'backup', 'invalid_customer_actor', 'test');
    raise exception 'customer actor accepted admin actor_type';
  exception
    when check_violation then null;
  end;

  begin
    insert into audit_logs (
      actor_telegram_user_id, actor_kind, actor_type, action, target_type
    ) values (admin_id + 1, 'admin', null, 'invalid_admin_actor', 'test');
    raise exception 'admin actor accepted null actor_type';
  exception
    when check_violation then null;
  end;
end $$;
