begin;

select plan(6);

select lives_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id
) values (910000001, 'admin', 'primary', 'test_admin_actor', 'test', 'admin')$$,
'admin audit actor is accepted');

select lives_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, actor_type, action, target_type, target_id
) values (910000002, 'customer', null, 'test_customer_actor', 'test', 'customer')$$,
'customer audit actor is accepted');

select throws_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, actor_type, action, target_type
) values (910000003, 'customer', 'backup', 'invalid_customer_actor', 'test')$$,
'23514',
'new row for relation "audit_logs" violates check constraint "audit_actor_contract"',
'customer actor cannot have admin actor type');

select throws_ok($$insert into audit_logs (
  actor_telegram_user_id, actor_kind, actor_type, action, target_type
) values (910000004, 'admin', null, 'invalid_admin_actor', 'test')$$,
'23514',
'new row for relation "audit_logs" violates check constraint "audit_actor_contract"',
'admin actor requires actor type');

select is(
  (select count(*)::integer from audit_logs
   where actor_telegram_user_id in (910000001,910000002)
     and action in ('test_admin_actor','test_customer_actor')),
  2,
  'valid audit actor records persisted');

select * from finish();
rollback;
