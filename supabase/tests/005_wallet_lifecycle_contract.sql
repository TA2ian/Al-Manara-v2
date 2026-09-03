begin;

select plan(8);

select ok(to_regclass('public.wallets') is not null, 'wallet table exists');
select ok(
    exists (
        select 1 from information_schema.columns
         where table_schema='public' and table_name='wallets' and column_name='label'
    ),
    'wallet label is persisted'
);
select ok(
    exists (
        select 1 from information_schema.columns
         where table_schema='public' and table_name='wallets' and column_name='qr_image_file_id'
    ),
    'wallet QR file id is persisted'
);
select ok(
    to_regprocedure('public.delete_wallet_if_allowed(uuid,uuid)') is not null,
    'wallet deletion operation exists'
);

insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000009901', 9900000001);

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
values
    ('00000000-0000-0000-0000-000000009902', '00000000-0000-0000-0000-000000009901', 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'VERIFIED', 'Primary', 'QR-9902', now()),
    ('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000009901', 'TRC20', 'T11111111111111111111111111111111', 't11111111111111111111111111111111', 'VERIFIED', 'Secondary', 'QR-9903', now());

select throws_ok(
    $$insert into wallets (user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
      values ('00000000-0000-0000-0000-000000009901', 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'VERIFIED', 'Duplicate', 'QR-DUP', now())$$,
    '23505',
    'duplicate normalized wallet address is rejected'
);

select throws_ok(
    $$update wallets set label='Changed' where id='00000000-0000-0000-0000-000000009902'$$,
    'verified wallets are immutable%',
    'verified wallet fields cannot be changed'
);

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status, version)
select '00000000-0000-0000-0000-000000009904', 'ORD-WALLET-9904',
       '00000000-0000-0000-0000-000000009901',
       '00000000-0000-0000-0000-000000009902',
       'BEP20', id, 'APPROVED', 1
from payment_methods where code='SHAM_CASH';

select throws_ok(
    $$delete from wallets where id='00000000-0000-0000-0000-000000009902'$$,
    'wallet is linked to an active order%',
    'wallet linked to an active order cannot be deleted'
);

select is(
    delete_wallet_if_allowed('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000009901'),
    true,
    'verified wallet without active orders can be deleted'
);

select is(
    delete_wallet_if_allowed('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000009901'),
    false,
    'deleting an already absent wallet is idempotently false'
);

select * from finish();
rollback;
