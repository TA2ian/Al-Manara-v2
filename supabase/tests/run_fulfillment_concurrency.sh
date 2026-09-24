#!/usr/bin/env bash
set -euo pipefail

DB_URL="${SUPABASE_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

psql_cmd() {
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X "$@"
}

echo "Preparing concurrency fixtures..."
psql_cmd <<'SQL'
insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values
  (29001001, 'primary', true, false),
  (29001002, 'backup', true, true);

insert into users (id, telegram_user_id)
values
  ('00000000-0000-0000-0000-000000009001', 29002001);

insert into wallets (
  id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id
) values
  (
    '00000000-0000-0000-0000-000000009011',
    '00000000-0000-0000-0000-000000009001',
    'BEP20',
    '0x0000000000000000000000000000000000009001',
    '0x0000000000000000000000000000000000009001',
    'VERIFIED',
    'concurrency test',
    'QR-9001'
  );

insert into admin_sessions (id, admin_telegram_user_id, expires_at)
values
  ('00000000-0000-0000-0000-000000009031', 29001001, now() + interval '10 minutes');

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id,
  network_code, payment_method_id, status, version
)
select
  '00000000-0000-0000-0000-000000009021',
  'ORD-CONC-1',
  '00000000-0000-0000-0000-000000009001',
  '00000000-0000-0000-0000-000000009011',
  'BEP20',
  id,
  'APPROVED',
  1
from payment_methods
where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, local_amount,
  rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000009021',
  100, 10, 10, 0.15, 89.85, 'USD', 100, 'test', 1
);

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id,
  network_code, payment_method_id, status, version
)
select
  '00000000-0000-0000-0000-000000009022',
  'ORD-CONC-2',
  '00000000-0000-0000-0000-000000009001',
  '00000000-0000-0000-0000-000000009011',
  'BEP20',
  id,
  'APPROVED',
  1
from payment_methods
where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, local_amount,
  rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000009022',
  100, 10, 10, 0.15, 89.85, 'USD', 100, 'test', 1
);

insert into orders (
  internal_order_id, public_order_code, user_id, wallet_id,
  network_code, payment_method_id, status, version
)
select
  '00000000-0000-0000-0000-000000009023',
  'ORD-CONC-3',
  '00000000-0000-0000-0000-000000009001',
  '00000000-0000-0000-0000-000000009011',
  'BEP20',
  id,
  'APPROVED',
  1
from payment_methods
where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount,
  network_fee_amount, net_usdt_amount, payment_currency, local_amount,
  rounding_policy_version, network_config_version
) values (
  '00000000-0000-0000-0000-000000009023',
  100, 10, 10, 0.15, 89.85, 'USD', 100, 'test', 1
);
SQL

run_same_key_completion() {
  local order_id="00000000-0000-0000-0000-000000009021"
  local key="concurrency-complete-same-key"
  local txid="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

  (
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/a.out" 2>"$TMP_DIR/a.err" <<SQL
begin;
select internal_order_id
  from orders
 where internal_order_id = '$order_id'
 for update;
select pg_sleep(2);
select replayed
  from complete_order_fulfillment(
    '$order_id', 1, 29001001, 'primary', '$key',
    '00000000-0000-0000-0000-000000009031', '$txid'
  );
commit;
SQL
  ) &
  local pid_a=$!

  sleep 0.5

  (
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/b.out" 2>"$TMP_DIR/b.err" <<SQL
select replayed
  from complete_order_fulfillment(
    '$order_id', 1, 29001001, 'primary', '$key',
    '00000000-0000-0000-0000-000000009031', '$txid'
  );
SQL
  ) &
  local pid_b=$!

  wait "$pid_a"
  wait "$pid_b"

  grep -Eq '^f$' "$TMP_DIR/a.out"
  grep -Eq '^t$' "$TMP_DIR/b.out"

  psql_cmd <<SQL
do $$
begin
  if (select version from orders where internal_order_id = '$order_id') <> 2 then
    raise exception 'same-key completion changed version more than once';
  end if;
  if (select status::text from orders where internal_order_id = '$order_id') <> 'COMPLETED' then
    raise exception 'same-key completion did not complete order';
  end if;
  if (select count(*) from order_fulfillment_idempotency
      where internal_order_id = '$order_id' and operation = 'complete') <> 1 then
    raise exception 'same-key completion created duplicate idempotency rows';
  end if;
  if (select count(*) from audit_logs
      where target_id = '$order_id' and action = 'order.fulfillment_completed') <> 1 then
    raise exception 'same-key completion created duplicate completion audit events';
  end if;
end
$$;
SQL
}

run_different_key_completion() {
  local order_id="00000000-0000-0000-0000-000000009022"

  (
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/c.out" 2>"$TMP_DIR/c.err" <<SQL
select * from claim_order_fulfillment(
  '$order_id', 1, 29001001, 'primary', 'concurrency-claim-for-complete',
  '00000000-0000-0000-0000-000000009031'
);
begin;
select internal_order_id
  from orders
 where internal_order_id = '$order_id'
 for update;
select pg_sleep(2);
select replayed
  from complete_order_fulfillment(
    '$order_id', 2, 29001001, 'primary', 'concurrency-complete-key-a',
    '00000000-0000-0000-0000-000000009031',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
  );
commit;
SQL
  ) &
  local pid_a=$!

  sleep 0.5

  (
    set +e
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/d.out" 2>"$TMP_DIR/d.err" <<SQL
select replayed
  from complete_order_fulfillment(
    '$order_id', 2, 29001001, 'primary', 'concurrency-complete-key-b',
    '00000000-0000-0000-0000-000000009031',
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
  );
SQL
    printf '%s' "$?" >"$TMP_DIR/d.status"
  ) &
  local pid_b=$!

  wait "$pid_a"
  wait "$pid_b"

  grep -q "stale order version" "$TMP_DIR/d.err"
  test "$(cat "$TMP_DIR/d.status")" -ne 0

  psql_cmd <<SQL
do $$
begin
  if (select version from orders where internal_order_id = '$order_id') <> 3 then
    raise exception 'different-key completion changed version unexpectedly';
  end if;
  if (select status::text from orders where internal_order_id = '$order_id') <> 'COMPLETED' then
    raise exception 'different-key completion did not complete order';
  end if;
  if (select manual_usdt_transfer_reference from orders where internal_order_id = '$order_id')
       <> 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' then
    raise exception 'different-key completion stored the wrong transfer reference';
  end if;
end
$$;
SQL
}

run_same_key_claim() {
  local order_id="00000000-0000-0000-0000-000000009023"
  local key="concurrency-claim-same-key"

  (
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/e.out" 2>"$TMP_DIR/e.err" <<SQL
begin;
select internal_order_id
  from orders
 where internal_order_id = '$order_id'
 for update;
select pg_sleep(2);
select replayed
  from claim_order_fulfillment(
    '$order_id', 1, 29001001, 'primary', '$key'
  );
commit;
SQL
  ) &
  local pid_a=$!

  sleep 0.5

  (
    psql "$DB_URL" -v ON_ERROR_STOP=1 -X >"$TMP_DIR/f.out" 2>"$TMP_DIR/f.err" <<SQL
select replayed
  from claim_order_fulfillment(
    '$order_id', 1, 29001001, 'primary', '$key'
  );
SQL
  ) &
  local pid_b=$!

  wait "$pid_a"
  wait "$pid_b"

  grep -Eq '^f$' "$TMP_DIR/e.out"
  grep -Eq '^t$' "$TMP_DIR/f.out"

  psql_cmd <<SQL
do $$
begin
  if (select version from orders where internal_order_id = '$order_id') <> 2 then
    raise exception 'same-key claim changed version more than once';
  end if;
  if (select count(*) from order_fulfillment_claims where internal_order_id = '$order_id') <> 1 then
    raise exception 'same-key claim did not leave exactly one active claim';
  end if;
  if (select count(*) from order_fulfillment_idempotency
      where internal_order_id = '$order_id' and operation = 'claim') <> 1 then
    raise exception 'same-key claim created duplicate idempotency rows';
  end if;
end
$$;
SQL
}

echo "1/3 same-key completion..."
run_same_key_completion
echo "PASS: same-key completion replays safely."

echo "2/3 different-key completion..."
run_different_key_completion
echo "PASS: different-key completion serializes and rejects the stale request."

echo "3/3 same-key claim..."
run_same_key_claim
echo "PASS: same-key claim replays safely."

echo "Concurrency integration tests passed."
