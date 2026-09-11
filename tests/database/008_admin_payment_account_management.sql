-- Contract checks for administrator payment-account management.
begin;

select plan(8);

select has_function('public', 'assert_enabled_admin', array['bigint','admin_actor_type'], 'admin identity helper exists');
select has_function('public', 'list_admin_payment_accounts', array['bigint','admin_actor_type'], 'admin payment account listing exists');
select has_function('public', 'upsert_admin_payment_account', array['bigint','admin_actor_type','currency_code','text','text','text'], 'admin payment account upsert exists');
select has_function('public', 'set_admin_payment_account_active', array['bigint','admin_actor_type','currency_code','boolean'], 'admin payment account status update exists');

select is(
    has_function_privilege('anon', 'public.upsert_admin_payment_account(bigint,admin_actor_type,currency_code,text,text,text)', 'EXECUTE'),
    false,
    'anon cannot execute payment-account mutation'
);
select is(
    has_function_privilege('authenticated', 'public.upsert_admin_payment_account(bigint,admin_actor_type,currency_code,text,text,text)', 'EXECUTE'),
    false,
    'authenticated cannot execute payment-account mutation'
);
select is(
    has_function_privilege('service_role', 'public.upsert_admin_payment_account(bigint,admin_actor_type,currency_code,text,text,text)', 'EXECUTE'),
    true,
    'service_role can execute payment-account mutation'
);
select is(
    has_function_privilege('service_role', 'public.list_admin_payment_accounts(bigint,admin_actor_type)', 'EXECUTE'),
    true,
    'service_role can execute payment-account listing'
);

select * from finish();
rollback;
