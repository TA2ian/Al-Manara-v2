begin;

select plan(70);

select ok((select count(*) from pg_proc where proname = 'reserve_receipt_submission') = 1, 'canonical receipt reservation RPC exists');
select ok((select count(*) from pg_proc where proname = 'finalize_receipt_submission') = 1, 'canonical receipt finalization RPC exists');
select ok(position('PAYMENT_SUBMITTED' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'finalize_receipt_submission' limit 1))) > 0, 'successful receipt finalization advances the order to PAYMENT_SUBMITTED');
select ok(position('UNDER_REVIEW' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'finalize_receipt_submission' limit 1))) > 0, 'successful receipt finalization enters the human review queue');
select ok((select count(*) from pg_proc where proname = 'list_verified_wallets_for_telegram_user') = 1, 'verified wallet listing RPC exists');
select ok((select count(*) from pg_proc where proname = 'register_pending_wallet_for_telegram_user') = 1, 'pending wallet registration RPC exists');
select ok((select count(*) from pg_proc where proname = 'disable_wallet_for_telegram_user') = 1, 'wallet disable RPC exists');
select ok((select count(*) from pg_proc where proname = 'transition_order_if_version') = 1, 'canonical order transition RPC exists');
select ok(position('from admin_users au' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'transition_order_if_version' limit 1))) > 0, 'order transition RPC verifies supplied admin actors against admin_users');
select ok((select count(*) from pg_proc where proname = 'get_order_for_transition') = 1, 'order transition read RPC exists');
select ok((select count(*) from pg_proc where proname = 'authorize_admin_order_review') = 1, 'admin order review authorization RPC exists');
select ok((select count(*) from pg_proc where proname = 'transition_order_idempotent') = 1, 'atomic idempotent admin transition RPC exists');
select ok(position('on conflict (idempotency_key) do nothing' in lower(pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'transition_order_idempotent' limit 1)))) > 0, 'atomic transition reserves idempotency keys safely under concurrency');
select ok(to_regclass('public.order_transition_idempotency') is not null, 'order transition idempotency table exists');
select ok((select count(*) from pg_proc where proname = 'claim_order_fulfillment') = 1, 'atomic fulfillment claim RPC exists');
select ok(position('APPROVED' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0, 'fulfillment claim is restricted to APPROVED orders');
select ok(position('order_fulfillment_claims' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0, 'fulfillment claim persists an active claim');
select ok((select count(*) from pg_proc where proname = 'complete_order_fulfillment') = 1, 'atomic fulfillment completion RPC exists');
select ok(position('active fulfillment claim is required' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0, 'fulfillment completion requires an active claim');
select ok(to_regclass('public.order_fulfillment_idempotency') is not null, 'fulfillment idempotency table exists');
select ok(exists (select 1 from pg_trigger where tgname = 'orders_fulfillment_completion_guard' and tgrelid = 'public.orders'::regclass and tgenabled = 'O'), 'database completion guard trigger exists');
select ok(position('order_fulfillment_idempotency' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'enforce_fulfillment_completion_guard' limit 1))) > 0, 'completion guard requires a durable fulfillment completion record');
select ok((select count(*) from pg_proc where proname = 'close_order_without_fulfillment') = 1, 'administrative no-fulfillment closure RPC exists');
select ok(to_regclass('public.admin_sessions') is not null and to_regclass('public.order_fulfillment_claims') is not null, 'administrative session and fulfillment claim tables exist');
select ok(position('admin session is invalid or expired' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'close_order_without_fulfillment' limit 1))) > 0, 'administrative closure requires a valid session');
select ok(position('from admin_users au' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'close_order_without_fulfillment' limit 1))) < position('select ik.response_json' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'close_order_without_fulfillment' limit 1))), 'closure authorizes the admin before idempotency replay');
select ok((select count(*) from pg_proc where proname = 'list_admin_orders') = 1, 'authorized admin order listing RPC exists');
select ok(position('admin_users au' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_orders' limit 1))) > 0, 'admin order listing is database-authorized');
select ok(position('PENDING_PAYMENT' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_orders' limit 1))) > 0, 'admin order listing exposes pending orders through canonical status');
select ok(position('UNDER_REVIEW' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_orders' limit 1))) > 0, 'admin order listing exposes the human review queue');
select ok((select count(*) from pg_proc where proname = 'create_admin_session') = 1, 'admin session creation RPC exists');
select ok((select count(*) from pg_proc where proname = 'revoke_admin_session') = 1, 'admin session revocation RPC exists');
select ok(position('admin_session_timeout_seconds' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'create_admin_session' limit 1))) > 0, 'admin session lifetime is settings-driven');
select ok(position('admin.session.revoked' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'revoke_admin_session' limit 1))) > 0, 'admin session revocation is audited');

-- Quote support is sourced from authoritative persisted configuration.
select ok((select count(*) from pg_proc where proname = 'get_current_fee_policy') = 1, 'current fee policy RPC exists');
select ok(position('service_fee_percent' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'get_current_fee_policy' limit 1))) > 0, 'fee policy RPC reads persisted network fee configuration');
select ok((select count(*) from pg_proc where proname = 'get_current_exchange_rate') = 1, 'current exchange rate RPC exists');
select ok(position('active_exchange_rate_id' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'get_current_exchange_rate' limit 1))) > 0, 'exchange rate RPC follows the configured active rate');
select ok((select count(*) from pg_proc where proname = 'get_current_rounding_policy') = 1, 'current rounding policy RPC exists');
select ok(position('rounding_policy_version' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'get_current_rounding_policy' limit 1))) > 0, 'rounding policy RPC reads persisted policy configuration');

-- Privileged RPCs must be callable by the backend service role only.
select ok(not has_function_privilege('anon', 'public.get_order_for_transition(uuid)', 'execute'), 'order transition read RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_customer_payment_identity(bigint)', 'execute'), 'customer identity RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_admin_payment_account(currency_code)', 'execute'), 'admin payment account RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_network_config(network_code)', 'execute'), 'network config RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.create_purchase_order_atomic(uuid,text,bigint,uuid,text,text,numeric,numeric,numeric,numeric,text,numeric,numeric,text,text,text,text,text,text,timestamptz,timestamptz,text,text)', 'execute'), 'atomic order creation RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_wallet_for_telegram_user(uuid,bigint)', 'execute'), 'wallet read RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.find_verified_wallet_by_address(text)', 'execute'), 'wallet address lookup RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.list_verified_wallets_for_telegram_user(bigint)', 'execute'), 'wallet listing RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.register_pending_wallet_for_telegram_user(bigint,text,network_code,text,text)', 'execute'), 'wallet registration RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.disable_wallet_for_telegram_user(uuid,bigint)', 'execute'), 'wallet disable RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.reserve_receipt_submission(uuid,bigint,text,text,text,timestamptz)', 'execute'), 'receipt reservation RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.finalize_receipt_submission(uuid,text,text,text)', 'execute'), 'receipt finalization RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.authorize_admin_order_review(bigint,admin_actor_type)', 'execute'), 'admin authorization RPC is not publicly executable');
select ok(not has_function_privilege('authenticated', 'public.authorize_admin_order_review(bigint,admin_actor_type)', 'execute'), 'admin authorization RPC is not authenticated-user executable');
select ok(not has_function_privilege('anon', 'public.transition_order_if_version(uuid,order_status,bigint,bigint,admin_actor_type,jsonb)', 'execute'), 'generic privileged transition RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.transition_order_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,jsonb,text)', 'execute'), 'idempotent admin transition RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)', 'execute'), 'fulfillment claim RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)', 'execute'), 'fulfillment completion RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.close_order_without_fulfillment(uuid,bigint,bigint,uuid,text,text)', 'execute'), 'closure RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.list_admin_orders(bigint,admin_actor_type,text,integer,integer)', 'execute'), 'admin listing RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.create_admin_session(bigint,admin_actor_type)', 'execute'), 'admin session creation RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.revoke_admin_session(bigint,admin_actor_type,uuid)', 'execute'), 'admin session revocation RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_current_fee_policy(network_code,timestamptz)', 'execute'), 'fee policy RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_current_exchange_rate(text,timestamptz)', 'execute'), 'exchange rate RPC is not publicly executable');
select ok(not has_function_privilege('anon', 'public.get_current_rounding_policy()', 'execute'), 'rounding policy RPC is not publicly executable');

select ok(not has_function_privilege('authenticated', 'public.create_purchase_order_atomic(uuid,text,bigint,uuid,text,text,numeric,numeric,numeric,numeric,text,numeric,numeric,text,text,text,text,text,timestamptz,timestamptz,text,text)', 'execute') and not has_function_privilege('authenticated', 'public.reserve_receipt_submission(uuid,bigint,text,text,text,timestamptz)', 'execute') and not has_function_privilege('authenticated', 'public.list_verified_wallets_for_telegram_user(bigint)', 'execute'), 'customer backend RPCs are not authenticated-user executable');
select ok(has_function_privilege('service_role', 'public.get_order_for_transition(uuid)', 'execute') and has_function_privilege('service_role', 'public.create_purchase_order_atomic(uuid,text,bigint,uuid,text,text,numeric,numeric,numeric,numeric,text,numeric,numeric,text,text,text,text,timestamptz,timestamptz,text,text)', 'execute') and has_function_privilege('service_role', 'public.reserve_receipt_submission(uuid,bigint,text,text,text,timestamptz)', 'execute') and has_function_privilege('service_role', 'public.list_admin_orders(bigint,admin_actor_type,text,integer,integer)', 'execute') and has_function_privilege('service_role', 'public.get_current_fee_policy(network_code,timestamptz)', 'execute') and has_function_privilege('service_role', 'public.get_current_exchange_rate(text,timestamptz)', 'execute') and has_function_privilege('service_role', 'public.get_current_rounding_policy()', 'execute'), 'backend service role retains persistence and privileged RPC execution');

select * from finish();
rollback;
