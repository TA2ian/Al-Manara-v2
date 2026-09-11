begin;

select plan(13);

select ok(to_regprocedure('list_admin_fulfillment_orders(bigint,admin_actor_type,integer,integer)') is not null, 'claim-aware fulfillment listing RPC exists');
select ok(position('fulfillment_claimed_by' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1))) > 0, 'fulfillment listing exposes claim ownership');
select ok(position('order_fulfillment_claims' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1))) > 0, 'fulfillment listing reads authoritative claim ownership');
select ok(position('o.status = ''APPROVED''' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1))) > 0, 'fulfillment listing is restricted to APPROVED orders');
select ok(position('au.actor_type = p_actor_type' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1))) > 0, 'fulfillment listing authorizes the supplied admin actor type');
select ok(position('au.enabled' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1))) > 0, 'fulfillment listing rejects disabled administrators');
select ok(position('security invoker' in lower(pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'list_admin_fulfillment_orders' limit 1)))) > 0, 'fulfillment listing executes with invoker security context');
select ok(position('p_expected_version' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0 and position('stale order version' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0, 'claim operation enforces the optimistic version guard');
select ok(position('v_claim_admin <> p_admin_telegram_user_id' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0, 'completion verifies the authoritative claim owner');
select ok(position('for update' in lower(pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1)))) > 0 and position('for update' in lower(pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1)))) > 0, 'claim and completion serialize on authoritative rows');
select ok(position('order_fulfillment_idempotency' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0 and position('replayed' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0, 'fulfillment mutations persist and replay idempotent results');
select ok(position('idempotency key belongs to another fulfillment operation' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0 and position('idempotency key belongs to another fulfillment operation' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0, 'idempotency keys cannot be reused for another fulfillment operation');
select ok(position('order changed concurrently' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'claim_order_fulfillment' limit 1))) > 0 and position('order changed concurrently' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'complete_order_fulfillment' limit 1))) > 0, 'claim and completion reject concurrent version changes');

select * from finish();
rollback;
