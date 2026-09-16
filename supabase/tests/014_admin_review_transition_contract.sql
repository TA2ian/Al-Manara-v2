begin;

select plan(11);

select ok(
    not p.prosecdef,
    'admin review transition executes with invoker security context'
)
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname = 'admin_review_order_transition_idempotent'
limit 1;

select ok(
    has_function_privilege('public', 'admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid)', 'EXECUTE') = false,
    'public cannot execute admin review transition'
);

select ok(
    has_function_privilege('service_role', 'admin_review_order_transition_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,text,jsonb,uuid)', 'EXECUTE'),
    'service_role can execute admin review transition'
);

with fn as (
    select pg_get_functiondef(p.oid) as body
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'admin_review_order_transition_idempotent'
    limit 1
)
select ok(
    position('s.revoked_at is null' in body) > 0
    and position('s.expires_at > now()' in body) > 0
    and position('s.admin_telegram_user_id = p_admin_telegram_user_id' in body) > 0
    and position('v_registered_actor_type <> p_actor_type' in body) > 0,
    'admin review transition binds an active session to the authoritative admin actor'
) from fn;

insert into admin_users(telegram_user_id, actor_type, enabled, emergency_only)
values
    (910000001, 'primary', true, false),
    (910000002, 'backup', true, true);

insert into users(telegram_user_id)
values (910000101);

insert into wallets(user_id, network_code, address, normalized_address, status)
select id, 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'VERIFIED'
from users
where telegram_user_id = 910000101;

insert into orders(
    public_order_code,
    user_id,
    wallet_id,
    network_code,
    payment_method_id,
    status,
    version
)
select
    'ORD-ADMIN-REVIEW-01',
    u.id,
    w.id,
    'BEP20',
    pm.id,
    'UNDER_REVIEW',
    1
from users u
join wallets w on w.user_id = u.id
join payment_methods pm on pm.code = 'SHAM_CASH'
where u.telegram_user_id = 910000101;

create temporary table _admin_review_session(session_id uuid) on commit drop;
insert into _admin_review_session
select session_id from create_admin_session(910000001, 'primary');

create temporary table _admin_review_result on commit drop as
select *
from admin_review_order_transition_idempotent(
    (select internal_order_id from orders where public_order_code = 'ORD-ADMIN-REVIEW-01'),
    'APPROVED',
    1,
    910000001,
    'primary',
    'admin-review-contract-001',
    '{}'::jsonb,
    (select session_id from _admin_review_session)
);

select is(
    (select status::text from _admin_review_result),
    'APPROVED',
    'admin review atomically approves the under-review order'
);

select is(
    (select version from _admin_review_result),
    2::bigint,
    'admin review increments the order version exactly once'
);

select is(
    (select state_before::text from _admin_review_result),
    'UNDER_REVIEW',
    'admin review records the correct previous state'
);

select is(
    (select count(*)::integer from audit_logs
      where actor_telegram_user_id = 910000001
        and action = 'order.admin_reviewed'
        and target_id = (select internal_order_id::text from orders where public_order_code = 'ORD-ADMIN-REVIEW-01')),
    1,
    'admin review writes exactly one audit record'
);

create temporary table _admin_review_replay on commit drop as
select *
from admin_review_order_transition_idempotent(
    (select internal_order_id from orders where public_order_code = 'ORD-ADMIN-REVIEW-01'),
    'APPROVED',
    1,
    910000001,
    'primary',
    'admin-review-contract-001',
    '{}'::jsonb,
    (select session_id from _admin_review_session)
);

select is(
    (select version from _admin_review_replay),
    2::bigint,
    'admin review replays the committed idempotent result without a second transition'
);

select is(
    (select count(*)::integer from audit_logs
      where actor_telegram_user_id = 910000001
        and action = 'order.admin_reviewed'
        and target_id = (select internal_order_id::text from orders where public_order_code = 'ORD-ADMIN-REVIEW-01')),
    1,
    'idempotent replay does not duplicate the audit record'
);

update admin_sessions
set revoked_at = now()
where id = (select session_id from _admin_review_session);

create temporary table _revoked_replay_check(ok boolean) on commit drop;
do $$
begin
    begin
        perform admin_review_order_transition_idempotent(
            (select internal_order_id from orders where public_order_code = 'ORD-ADMIN-REVIEW-01'),
            'APPROVED',
            1,
            910000001,
            'primary',
            'admin-review-contract-001',
            '{}'::jsonb,
            (select session_id from _admin_review_session)
        );
        insert into _revoked_replay_check values (false);
    exception when others then
        insert into _revoked_replay_check values (true);
    end;
end;
$$;

select ok(
    (select ok from _revoked_replay_check limit 1),
    'revoked admin session cannot replay a privileged review result'
);

select * from finish();
rollback;
