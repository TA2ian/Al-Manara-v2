-- The session-bound review overload supersedes the legacy signature.
-- Remove the legacy entry point so there is no privileged path without a session.

revoke execute on function transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text) from public, service_role;
drop function if exists transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text);
