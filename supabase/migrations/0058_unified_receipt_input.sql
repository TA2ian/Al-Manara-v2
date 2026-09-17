-- Unify customer receipt submissions into one discriminated model.
-- Existing image rows remain valid; legacy shamcash_operation_number is retained for compatibility.

alter table receipt_submissions
    add column if not exists input_type text not null default 'IMAGE',
    add column if not exists transaction_reference text;

update receipt_submissions
   set transaction_reference = nullif(btrim(shamcash_operation_number), '')
 where transaction_reference is null
   and shamcash_operation_number is not null;

alter table receipt_submissions
    drop constraint if exists receipt_submissions_input_type_check;
alter table receipt_submissions
    add constraint receipt_submissions_input_type_check
    check (input_type in ('TEXT', 'IMAGE'));

alter table receipt_submissions
    drop constraint if exists receipt_submissions_transaction_reference_check;
alter table receipt_submissions
    add constraint receipt_submissions_transaction_reference_check
    check (
        transaction_reference is null
        or (
            length(btrim(transaction_reference)) between 1 and 128
            and transaction_reference !~ '[[:cntrl:]]'
        )
    );

alter table receipt_submissions
    drop constraint if exists receipt_submissions_input_shape_check;
alter table receipt_submissions
    add constraint receipt_submissions_input_shape_check
    check (
        (input_type = 'TEXT'
            and transaction_reference is not null
            and telegram_file_id is null
            and mime_type is null)
        or
        (input_type = 'IMAGE'
            and transaction_reference is null
            and telegram_file_id is not null
            and mime_type in ('image/jpeg', 'image/png', 'image/webp'))
    );

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
    if p_input_type not in ('TEXT', 'IMAGE') then raise exception 'invalid receipt input type'; end if;
    if p_submitted_at is null then raise exception 'submission time is required'; end if;

    v_reference := nullif(btrim(p_transaction_reference), '');
    v_file_id := nullif(btrim(p_telegram_file_id), '');
    v_mime := lower(nullif(btrim(p_mime_type), ''));

    if p_input_type = 'TEXT' then
        if v_reference is null or length(v_reference) > 128 then raise exception 'text receipt requires a transaction reference'; end if;
        if v_reference ~ '[[:cntrl:]]' then raise exception 'transaction reference contains control characters'; end if;
        if v_file_id is not null or v_mime is not null then raise exception 'text receipt cannot contain image fields'; end if;
    else
        if v_file_id is null then raise exception 'image receipt requires a file id'; end if;
        if v_mime not in ('image/jpeg', 'image/png', 'image/webp') then raise exception 'unsupported receipt image type'; end if;
        if v_reference is not null then raise exception 'image receipt cannot contain a transaction reference'; end if;
    end if;

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
        btrim(p_idempotency_key), p_input_type, v_reference, v_reference,
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

-- PostgreSQL cannot change a function's declared return type with CREATE OR REPLACE.
-- Drop the legacy signature before recreating the unified result contract.
drop function if exists finalize_receipt_submission(uuid, text, text, text);

create function finalize_receipt_submission(
    p_submission_id uuid,
    p_processing_status text,
    p_linkage_status text default null,
    p_failure_reason text default null
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
    linkage_status text,
    failure_reason text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_order_id uuid;
    v_attempt_number integer;
    v_current_status text;
    v_linkage_status text;
    v_order_version bigint;
    v_public_order_code text;
    v_input_type text;
    v_transaction_reference text;
begin
    if p_processing_status not in ('SUCCEEDED', 'FAILED', 'ESCALATED') then
        raise exception 'invalid receipt processing status';
    end if;

    if p_linkage_status is not null
       and p_linkage_status not in ('PENDING', 'LINKED', 'BLOCKED', 'ADMIN_ESCALATION') then
        raise exception 'invalid receipt linkage status';
    end if;

    if p_processing_status in ('FAILED', 'ESCALATED')
       and length(btrim(coalesce(p_failure_reason, ''))) = 0 then
        raise exception 'failure reason is required';
    end if;

    select r.internal_order_id, r.attempt_number, r.processing_status,
           r.linkage_status, r.input_type, r.transaction_reference
      into v_order_id, v_attempt_number, v_current_status,
           v_linkage_status, v_input_type, v_transaction_reference
      from receipt_submissions r
     where r.id = p_submission_id
     for update;

    if not found then raise exception 'receipt submission not found'; end if;
    if v_current_status <> 'PROCESSING' then raise exception 'receipt submission is not processing'; end if;

    if p_processing_status = 'ESCALATED' and v_attempt_number <> 3 then
        raise exception 'only the third receipt attempt may escalate';
    end if;

    if p_processing_status = 'SUCCEEDED' then
        select o.status::text, o.version, o.public_order_code
          into v_current_status, v_order_version, v_public_order_code
          from orders o
         where o.internal_order_id = v_order_id
         for update;

        if not found then raise exception 'receipt order not found'; end if;
        if v_current_status <> 'PENDING_PAYMENT' then raise exception 'verified receipt requires order in PENDING_PAYMENT'; end if;

        if v_input_type = 'TEXT' then
            update orders as o
               set shamcash_operation_number = v_transaction_reference,
                   updated_at = now()
             where o.internal_order_id = v_order_id;
        end if;

        update orders as o
           set status = 'PAYMENT_SUBMITTED',
               version = o.version + 1,
               updated_at = now()
         where o.internal_order_id = v_order_id
           and o.version = v_order_version;

        if not found then raise exception 'order changed while submitting receipt'; end if;

        insert into audit_logs (
            actor_telegram_user_id, actor_type, action, target_type, target_id,
            old_value, new_value, metadata
        ) values (
            null, null, 'order.status_changed', 'order', v_order_id::text,
            jsonb_build_object('status', 'PENDING_PAYMENT', 'version', v_order_version),
            jsonb_build_object('status', 'PAYMENT_SUBMITTED', 'version', v_order_version + 1),
            jsonb_build_object('source', 'receipt_verification', 'submission_id', p_submission_id, 'public_order_code', v_public_order_code, 'input_type', v_input_type)
        );

        update orders as o
           set status = 'UNDER_REVIEW',
               version = o.version + 1,
               updated_at = now()
         where o.internal_order_id = v_order_id
           and o.version = v_order_version + 1;

        if not found then raise exception 'order changed while entering review queue'; end if;

        insert into audit_logs (
            actor_telegram_user_id, actor_type, action, target_type, target_id,
            old_value, new_value, metadata
        ) values (
            null, null, 'order.status_changed', 'order', v_order_id::text,
            jsonb_build_object('status', 'PAYMENT_SUBMITTED', 'version', v_order_version + 1),
            jsonb_build_object('status', 'UNDER_REVIEW', 'version', v_order_version + 2),
            jsonb_build_object('source', 'receipt_verification', 'submission_id', p_submission_id, 'public_order_code', v_public_order_code, 'input_type', v_input_type)
        );
    end if;

    update receipt_submissions as rs
       set processing_status = p_processing_status,
           linkage_status = case
               when p_processing_status = 'SUCCEEDED' then 'LINKED'
               else coalesce(p_linkage_status, rs.linkage_status)
           end,
           failure_reason = case
               when p_processing_status in ('FAILED', 'ESCALATED') then btrim(p_failure_reason)
               else null
           end,
           completed_at = now()
     where rs.id = p_submission_id;

    return query
    select r.id, r.internal_order_id, r.attempt_number,
           r.input_type, r.transaction_reference,
           r.telegram_file_id, r.mime_type, r.submitted_at,
           r.processing_status, r.linkage_status, r.failure_reason
      from receipt_submissions r
     where r.id = p_submission_id;
end;
$$;

revoke all on function reserve_receipt_submission(uuid, bigint, text, text, text, text, text, timestamptz) from public, anon, authenticated;
revoke all on function finalize_receipt_submission(uuid, text, text, text) from public, anon, authenticated;
grant execute on function reserve_receipt_submission(uuid, bigint, text, text, text, text, text, timestamptz) to service_role;
grant execute on function finalize_receipt_submission(uuid, text, text, text) to service_role;
