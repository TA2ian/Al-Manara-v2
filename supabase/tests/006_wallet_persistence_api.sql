begin;

select plan(9);

select ok(to_regprocedure('public.get_wallet_for_telegram_user(uuid,bigint)') is not null, 'wallet lookup RPC exists');
select ok(to_regprocedure('public.find_verified_wallet_by_address(text,public.network_code)') is not null, 'verified address lookup RPC exists');
select ok(to_regprocedure('public.disable_wallet_for_telegram_user(uuid,bigint)') is not null, 'wallet disable RPC exists');

insert into users (id, telegram_user_id)
values
    ('00000000-0000-0000-0000-000000009911', 9910000001),
    ('00000000-0000-0000-0000-000000009913', 9910000002);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
values
    ('00000000-0000-0000-0000-000000009912', '00000000-0000-0000-0000-000000009911', 'BEP20', '0x2222222222222222222222222222222222222222', '0x2222222222222222222222222222222222222222', 'VERIFIED', 'Primary', 'QR-9912', now()),
    ('00000000-0000-0000-0000-000000009914', '00000000-0000-0000-0000-000000009913', 'ETH', '0x2222222222222222222222222222222222222222', '0x2222222222222222222222222222222222222222', 'VERIFIED', 'Ethereum', 'QR-9914', now());

select is((select wallet_id from get_wallet_for_telegram_user('00000000-0000-0000-0000-000000009912', 9910000001)), '00000000-0000-0000-0000-000000009912'::uuid, 'wallet lookup resolves internal wallet id');
select is((select telegram_user_id from get_wallet_for_telegram_user('00000000-0000-0000-0000-000000009912', 9910000001)), 9910000001::bigint, 'wallet lookup preserves Telegram actor id');
select is((select wallet_id from find_verified_wallet_by_address(' 0x2222222222222222222222222222222222222222 ', 'BEP20')), '00000000-0000-0000-0000-000000009912'::uuid, 'verified wallet is found on requested EVM network');
select is((select wallet_id from find_verified_wallet_by_address(' 0x2222222222222222222222222222222222222222 ', 'ETH')), '00000000-0000-0000-0000-000000009914'::uuid, 'same EVM address can coexist on another network');

select is((select disabled from disable_wallet_for_telegram_user('00000000-0000-0000-0000-000000009912', 9910000001)), true, 'disable RPC delegates to lifecycle operation');
select is((select status::text from wallets where id='00000000-0000-0000-0000-000000009912'), 'DISABLED', 'disable RPC persists DISABLED state');

select * from finish();
rollback;
