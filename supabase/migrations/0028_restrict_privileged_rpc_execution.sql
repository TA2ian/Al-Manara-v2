-- Backend persistence RPCs are callable by the bot backend only.
-- Database authorization remains authoritative inside each function; this layer
-- prevents anonymous/authenticated PostgREST callers from invoking backend APIs.

-- Order reads/support and creation.
revoke execute on function get_order_for_transition(uuid) from public, anon, authenticated;
grant execute on function get_order_for_transition(uuid) to service_role;

revoke execute on function get_customer_payment_identity(bigint) from public, anon, authenticated;
grant execute on function get_customer_payment_identity(bigint) to service_role;

revoke execute on function get_admin_payment_account(currency_code) from public, anon, authenticated;
grant execute on function get_admin_payment_account(currency_code) to service_role;

revoke execute on function get_network_config(network_code) from public, anon, authenticated;
grant execute on function get_network_config(network_code) to service_role;

revoke execute on function create_purchase_order_atomic(uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text) from public, anon, authenticated;
grant execute on function create_purchase_order_atomic(uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text) to service_role;

-- Wallet persistence.
revoke execute on function get_wallet_for_telegram_user(uuid, bigint) from public, anon, authenticated;
grant execute on function get_wallet_for_telegram_user(uuid, bigint) to service_role;

revoke execute on function find_verified_wallet_by_address(text) from public, anon, authenticated;
grant execute on function find_verified_wallet_by_address(text) to service_role;

revoke execute on function list_verified_wallets_for_telegram_user(bigint) from public, anon, authenticated;
grant execute on function list_verified_wallets_for_telegram_user(bigint) to service_role;

revoke execute on function register_pending_wallet_for_telegram_user(bigint, text, network_code, text, text) from public, anon, authenticated;
grant execute on function register_pending_wallet_for_telegram_user(bigint, text, network_code, text, text) to service_role;

revoke execute on function disable_wallet_for_telegram_user(uuid, bigint) from public, anon, authenticated;
grant execute on function disable_wallet_for_telegram_user(uuid, bigint) to service_role;

-- Receipt persistence.
revoke execute on function reserve_receipt_submission(uuid, bigint, text, text, text, timestamptz) from public, anon, authenticated;
grant execute on function reserve_receipt_submission(uuid, bigint, text, text, text, timestamptz) to service_role;

revoke execute on function finalize_receipt_submission(uuid, text, text, text) from public, anon, authenticated;
grant execute on function finalize_receipt_submission(uuid, text, text, text) to service_role;

-- Privileged administrative RPCs.
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
