begin;
select plan(2);
select ok(to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,text,uuid)') is not null,'manual-reference completion RPC exists');
select ok(has_function_privilege('service_role','public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text,uuid)','EXECUTE') = false,'old completion RPC is disabled');
select * from finish();
rollback;
