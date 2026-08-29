-- Al-Manara v2 — atomic receipt-attempt reservation hardening
-- This migration serializes attempt allocation per order so concurrent inserts cannot
-- both observe the same existing attempt count.

create or replace function enforce_receipt_attempt_limit()
returns trigger
language plpgsql
as $$
declare
  existing_attempts integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(new.internal_order_id::text, 0));

  select count(*)
    into existing_attempts
  from receipt_submissions
  where internal_order_id = new.internal_order_id;

  if existing_attempts >= 3 then
    raise exception 'receipt attempt limit exceeded for order %', new.internal_order_id
      using errcode = 'check_violation';
  end if;

  if new.attempt_number <> existing_attempts + 1 then
    raise exception 'receipt attempt number must be sequential for order %', new.internal_order_id
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;
