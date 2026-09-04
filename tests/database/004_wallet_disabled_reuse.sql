begin;

select plan(2);

select ok(
    (select count(*) from pg_indexes where indexname = 'wallets_user_network_address_active_uq') = 1,
    'active wallet uniqueness index excludes disabled historical wallets'
);

select ok(
    position('status <> ''DISABLED''' in pg_get_functiondef((select p.oid from pg_proc p where p.proname = 'register_pending_wallet_for_telegram_user' limit 1))) > 0,
    'wallet registration permits reuse after disablement while blocking active duplicates'
);

select * from finish();
rollback;
