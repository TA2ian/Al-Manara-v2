begin;

select plan(6);

select lives_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_type, action, target_type, target_id
) values (910000011, 'primary', 'test_derived_admin_actor', 'test', '00000000-0000-0000-0000-000000000011')$$,
'legacy admin audit shape derives actor_kind');

select is(
  (select actor_kind from audit_logs
   where actor_telegram_user_id = 910000011
     and action = 'test_derived_admin_actor'),
  'admin',
  'derived admin actor kind is admin'
);

select lives_ok($$insert into audit_logs (
  actor_telegram_user_id, action, target_type, target_id
) values (910000012, 'test_derived_customer_actor', 'test', '00000000-0000-0000-0000-000000000012')$$,
'legacy customer audit shape derives actor_kind');

select is(
  (select actor_kind from audit_logs
   where actor_telegram_user_id = 910000012
     and action = 'test_derived_customer_actor'),
  'customer',
  'derived customer actor kind is customer'
);

select throws_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id
) values (910000013, 'customer', 'primary', 'test_mismatched_actor', 'test',
          '00000000-0000-0000-0000-000000000013')$$,
'P0001',
'audit actor kind does not match actor fields',
'contradictory explicit actor kind is rejected');

select throws_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, action, target_type, target_id
) values (910000014, 'admin', 'test_invalid_actor_kind', 'test',
          '00000000-0000-0000-0000-000000000014')$$,
'P0001',
'audit actor kind does not match actor fields',
'actor kind cannot be supplied without actor type');

select * from finish();
rollback;
