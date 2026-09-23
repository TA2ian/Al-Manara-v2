create or replace function reserve_next_receipt_attempt(
    p_order_id uuid,
    p_submitted_at timestamptz,
    p_mime_type text,
    p_telegram_file_id text
)
returns table (
    attempt_id uuid,
    order_id uuid,
    attempt_number smallint,
    mime_type text,
    telegram_file_id text,
    submitted_at timestamptz,
    status text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_status text;
    v_attempt_count integer;
    v_attempt_number smallint;
    v_attempt_id uuid;
begin
    if p_submitted_at is null then raise exception 'submission time is required'; end if;
    if p_mime_type not in ('image/jpeg', 'image/png', 'image/webp') then raise exception 'unsupported receipt image type'; end if;
    if p_telegram_file_id is null or length(btrim(p_telegram_file_id)) = 0 then raise exception 'receipt file id is required'; end if;

    select o.status into v_status
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_status <> 'awaiting_payment' then raise exception 'order does not accept receipts in current state'; end if;

    if exists (select 1 from receipt_attempts where order_id = p_order_id and status = 'processing') then
        raise exception 'receipt is already being processed';
    end if;

    select count(*)::integer into v_attempt_count
      from receipt_attempts
     where order_id = p_order_id;

    if v_attempt_count >= 3 then
        raise exception 'receipt attempt limit reached';
    end if;

    v_attempt_number := (v_attempt_count + 1)::smallint;
    v_attempt_id := gen_random_uuid();

    insert into receipt_attempts (
        attempt_id, order_id, attempt_number, mime_type, telegram_file_id, submitted_at, status
    ) values (
        v_attempt_id, p_order_id, v_attempt_number, btrim(p_mime_type), btrim(p_telegram_file_id), p_submitted_at, 'processing'
    );

    return query
    select r.attempt_id, r.order_id, r.attempt_number, r.mime_type, r.telegram_file_id, r.submitted_at, r.status
      from receipt_attempts r
     where r.attempt_id = v_attempt_id;
exception
    when unique_violation then
        raise exception 'receipt attempt reservation conflict';
end;
$$;

create or replace function finalize_receipt_attempt(
    p_attempt_id uuid,
    p_status text,
    p_failure_reason text default null
)
returns table (
    attempt_id uuid,
    order_id uuid,
    attempt_number smallint,
    status text,
    failure_reason text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_order_id uuid;
    v_attempt_number smallint;
    v_current_status text;
begin
    if p_status not in ('failed', 'verified', 'escalated') then raise exception 'invalid receipt final status'; end if;
    if p_status in ('failed', 'escalated') and length(btrim(coalesce(p_failure_reason, ''))) = 0 then
        raise exception 'failure reason is required';
    end if;

    select r.order_id, r.attempt_number, r.status
      into v_order_id, v_attempt_number, v_current_status
      from receipt_attempts r
     where r.attempt_id = p_attempt_id
     for update;
    if not found then raise exception 'receipt attempt not found'; end if;
    if v_current_status <> 'processing' then raise exception 'receipt attempt is not processing'; end if;
    if p_status = 'escalated' and v_attempt_number <> 3 then raise exception 'only third attempt may escalate'; end if;

    update receipt_attempts
       set status = p_status,
           failure_reason = case when p_status in ('failed', 'escalated') then btrim(p_failure_reason) else null end
     where attempt_id = p_attempt_id;

    return query
    select r.attempt_id, r.order_id, r.attempt_number, r.status, r.failure_reason
      from receipt_attempts r
     where r.attempt_id = p_attempt_id;
end;
$$;
