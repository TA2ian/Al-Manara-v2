-- Customer wallet lifecycle contract.
-- Verified wallets are immutable. Replacement is delete + add, but deletion is
-- forbidden while the wallet is referenced by any active order.

alter table wallets
    add column if not exists label text,
    add column if not exists qr_image_file_id text;

alter table wallets
    drop constraint if exists wallets_label_valid;
alter table wallets
    add constraint wallets_label_valid
    check (label is not null and length(btrim(label)) between 1 and 64);

alter table wallets
    drop constraint if exists wallets_qr_file_id_valid;
alter table wallets
    add constraint wallets_qr_file_id_valid
    check (qr_image_file_id is not null and length(btrim(qr_image_file_id)) > 0);

create or replace function prevent_verified_wallet_update() returns trigger
language plpgsql
as $$
begin
    if old.status = 'VERIFIED' then
        if new.user_id is distinct from old.user_id
           or new.network_code is distinct from old.network_code
           or new.address is distinct from old.address
           or new.normalized_address is distinct from old.normalized_address
           or new.status is distinct from old.status
           or new.label is distinct from old.label
           or new.qr_image_file_id is distinct from old.qr_image_file_id
           or new.verified_at is distinct from old.verified_at then
            raise exception 'verified wallets are immutable; delete and add a replacement';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists wallets_verified_immutable on wallets;
create trigger wallets_verified_immutable
before update on wallets
for each row execute function prevent_verified_wallet_update();

create or replace function prevent_active_order_wallet_delete() returns trigger
language plpgsql
as $$
begin
    if exists (
        select 1
          from orders o
         where o.wallet_id = old.id
           and o.status in (
               'DRAFT',
               'PENDING_PAYMENT',
               'PAYMENT_SUBMITTED',
               'UNDER_REVIEW',
               'APPROVED',
               'CLARIFICATION_REQUIRED'
           )
    ) then
        raise exception 'wallet is linked to an active order and cannot be deleted';
    end if;
    return old;
end;
$$;

drop trigger if exists wallets_active_order_delete_guard on wallets;
create trigger wallets_active_order_delete_guard
before delete on wallets
for each row execute function prevent_active_order_wallet_delete();

create or replace function delete_wallet_if_allowed(
    p_wallet_id uuid,
    p_user_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_deleted_count integer;
begin
    delete from wallets
     where id = p_wallet_id
       and user_id = p_user_id
       and status = 'VERIFIED';
    get diagnostics v_deleted_count = row_count;
    return v_deleted_count > 0;
end;
$$;
