-- MVP policy: customer receipt submission accepts images only.
-- Legacy TEXT data/schema is retained for compatibility, but new customer
-- submissions cannot create TEXT receipt attempts and verification never
-- derives an expected transaction reference from the order.

create or replace function reserve_receipt_submission(
    p_order_id uuid,
    p_telegram_user_id bigint,
    p_idempotency_key text,
    p_input_type text,
    p_transaction_reference text default null,
    p_telegram_file_id text default null,
    p_mime_type text default null,
    p_submitted_at timestamptz default now()
)
returns table (
    submission_id uuid,
    internal_order_id uuid,
    attempt_number integer,
    input_type text,
    transaction_reference text,
    telegram_file_id text,
    mime_type text,
    submitted_at timestamptz,
    processing_status text,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing receipt_submissions%rowtype;
    v_status order_status;
    v_attempt integer;
    v_submission_id uuid;
    v_reference text;
    v_file_id text;
    v_mime text;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_telegram_user_id is null or p_telegram_user_id <= 0 then raise exception 'telegram user id must be positive'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_input_type <> 'IMAGE' then raise exception 'customer receipt submission requires an image'; end if;
    if p_submitted_at is null then raise exception 'submission time is required'; end if;

    v_reference := nullif(btrim(p_transaction_reference), '');
    v_file_id := nullif(btrim(p_telegram_file_id), '');
    v_mime := lower(nullif(btrim(p_mime_type), ''));

    if v_file_id is null then raise exception 'image receipt requires a file id'; end if;
    if v_mime not in ('image/jpeg', 'image/png', 'image/webp') then raise exception 'unsupported receipt image type'; end if;
    if v_reference is not null then raise exception 'customer image receipt cannot contain a transaction reference'; end if;

    perform pg_advisory_xact_lock(hashtextextended(p_order_id::text, 0));

    select * into v_existing
      from receipt_submissions
     where idempotency_key = btrim(p_idempotency_key)
     for update;

    if found then
        if v_existing.internal_order_id <> p_order_id then
            raise exception 'idempotency key belongs to another order';
        end if;
        return query
        select v_existing.id, v_existing.internal_order_id, v_existing.attempt_number,
               v_existing.input_type, v_existing.transaction_reference,
               v_existing.telegram_file_id, v_existing.mime_type,
               v_existing.submitted_at, v_existing.processing_status, true;
        return;
    end if;

    select o.status into v_status
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_status <> 'PENDING_PAYMENT' then raise exception 'order does not accept receipts in current state'; end if;

    if exists (
        select 1 from receipt_submissions rs
         where rs.internal_order_id = p_order_id
           and rs.processing_status = 'PROCESSING'
    ) then
        raise exception 'receipt is already being processed';
    end if;

    select coalesce(max(rs.attempt_number), 0) + 1
      into v_attempt
      from receipt_submissions rs
     where rs.internal_order_id = p_order_id;

    if v_attempt > 3 then raise exception 'receipt attempt limit reached'; end if;

    v_submission_id := gen_random_uuid();

    insert into receipt_submissions (
        id, internal_order_id, source, attempt_number, idempotency_key,
        input_type, transaction_reference, shamcash_operation_number,
        telegram_file_id, mime_type, submitted_at, linkage_status, processing_status
    ) values (
        v_submission_id, p_order_id, 'customer', v_attempt,
        btrim(p_idempotency_key), 'IMAGE', null, null,
        v_file_id, v_mime, p_submitted_at, 'PENDING', 'PROCESSING'
    );

    return query
    select r.id, r.internal_order_id, r.attempt_number,
           r.input_type, r.transaction_reference,
           r.telegram_file_id, r.mime_type, r.submitted_at,
           r.processing_status, false
      from receipt_submissions r
     where r.id = v_submission_id;
end;
$$;

revoke all on function reserve_receipt_submission(uuid, bigint, text, text, text, text, text, timestamptz) from public, anon, authenticated;
grant execute on function reserve_receipt_submission(uuid, bigint, text, text, text, text, text, timestamptz) to service_role;

-- Do not use a customer-supplied transaction reference as expected verification
-- evidence. The image pipeline must establish evidence from the receipt itself.
create or replace function get_receipt_verification_snapshot(p_order_id uuid)
returns table (
    order_id uuid,
    payment_currency currency_code,
    expected_payment_amount numeric(24,9),
    exchange_rate numeric(24,9),
    fee_percent numeric(9,6),
    rounding_policy_version text,
    network_code network_code,
    wallet_address text,
    expected_reference text,
    tolerance numeric(24,9)
)
language sql
security invoker
set search_path = public
as $$
    select
        o.internal_order_id,
        s.payment_currency,
        s.local_amount,
        s.exchange_rate,
        s.fee_percent,
        s.rounding_policy_version,
        o.network_code,
        w.address,
        null::text,
        st.absolute_tolerance
    from orders o
    join order_financial_snapshots s
      on s.internal_order_id = o.internal_order_id
    join wallets w
      on w.id = o.wallet_id
     and w.user_id = o.user_id
    cross join settings st
    where o.internal_order_id = p_order_id
    limit 1;
$$;

revoke all on function get_receipt_verification_snapshot(uuid) from public;
grant execute on function get_receipt_verification_snapshot(uuid) to service_role;
