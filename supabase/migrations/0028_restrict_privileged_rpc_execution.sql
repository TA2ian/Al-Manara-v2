-- Privileged administrative RPCs are callable by the bot backend only.
-- Database authorization remains authoritative inside each function; this layer
-- prevents anonymous/authenticated PostgREST callers from invoking the RPCs at all.

revoke execute on function authorize_admin_order_review(bigint, admin_actor_type) from public, anon, authenticated;
grant execute on function authorize_admin_order_review(bigint, admin_actor_type) to service_role;

revoke execute on function transition_order_if_version(uuid, order_status, bigint, bigint, admin_actor_type, jsonb) from public, anon, authenticated;
grant execute on function transition_order_if_version(uuid, order_status, bigint, bigint, admin_actor_type, jsonb) to service_role;

revoke execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text) from public, anon, authenticated;
grant execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text) to service_role;

revoke execute on function claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) from public, anon, authenticated;
grant execute on function claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) to service_role;

revoke execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) from public, anon, authenticated;
grant execute on function complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) to service_role;

revoke execute on function close_order_without_fulfillment(uuid, bigint, bigint, uuid, text, text) from public, anon, authenticated;
grant execute on function close_order_without_fulfillment(uuid, bigint, bigint, uuid, text, text) to service_role;

revoke execute on function list_admin_orders(bigint, admin_actor_type, text, integer, integer) from public, anon, authenticated;
grant execute on function list_admin_orders(bigint, admin_actor_type, text, integer, integer) to service_role;

revoke execute on function create_admin_session(bigint, admin_actor_type) from public, anon, authenticated;
grant execute on function create_admin_session(bigint, admin_actor_type) to service_role;

revoke execute on function revoke_admin_session(bigint, admin_actor_type, uuid) from public, anon, authenticated;
grant execute on function revoke_admin_session(bigint, admin_actor_type, uuid) to service_role;
