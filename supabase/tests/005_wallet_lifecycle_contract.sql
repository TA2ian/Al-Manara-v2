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

insert into users (telegram_user_id)
values (9900000001)
returning id into strict _wallet_user_id;
