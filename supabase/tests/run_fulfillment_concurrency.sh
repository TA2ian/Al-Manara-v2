#!/usr/bin/env bash
set -euo pipefail

DB_URL="${SUPABASE_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

psql_cmd() {
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X "$@"
}

ADMIN=29001001
SESSION=00000000-0000-0000-0000-000000009031

echo "Preparing concurrency fixtures..."
psql_cmd <<'SQL'
insert into admin_users (telegram_user_id, actor_type, enabled, emergency_only)
values (29001001, 'primary', true, false), (29001002, 'backup', true, true);

insert into users (id, telegram_user_id) values
 ('00000000-0000-0000-0000-000000009001', 29002001),
 ('00000000-0000-0000-0000-000000009002', 29002002),
 ('00000000-0000-0000-0000-000000009003', 29002003);

insert into wallets (id,user_id,network_code,address,normalized_address,status,label,qr_image_file_id) values
 ('00000000-0000-0000-0000-000000009011','00000000-0000-0000-0000-000000009001','BEP20','0x0000000000000000000000000000000000009001','0x0000000000000000000000000000000000009001','VERIFIED','concurrency','QR-9001'),
 ('00000000-0000-0000-0000-000000009012','00000000-0000-0000-0000-000000009002','BEP20','0x0000000000000000000000000000000000009002','0x0000000000000000000000000000000000009002','VERIFIED','concurrency','QR-9002'),
 ('00000000-0000-0000-0000-000000009013','00000000-0000-0000-0000-000000009003','BEP20','0x0000000000000000000000000000000000009003','0x0000000000000000000000000000000000009003','VERIFIED','concurrency','QR-9003');

insert into admin_sessions (id,admin_telegram_user_id,expires_at)
values ('00000000-0000-0000-0000-000000009031',29001001,now()+interval '10 minutes');

insert into orders (internal_order_id,public_order_code,user_id,wallet_id,network_code,payment_method_id,status,version)
select '00000000-0000-0000-0000-000000009021','ORD-CONC-1','00000000-0000-0000-0000-000000009001','00000000-0000-0000-0000-000000009011','BEP20',id,'APPROVED',1 from payment_methods where code='SHAM_CASH';
insert into order_financial_snapshots (internal_order_id,requested_amount,fee_percent,fee_amount,network_fee_amount,net_usdt_amount,payment_currency,local_amount,rounding_policy_version,network_config_version)
values ('00000000-0000-0000-0000-000000009021',100,10,10,0.15,89.85,'USD',100,'test',1);

insert into orders (internal_order_id,public_order_code,user_id,wallet_id,network_code,payment_method_id,status,version)
select '00000000-0000-0000-0000-000000009022','ORD-CONC-2','00000000-0000-0000-0000-000000009002','00000000-0000-0000-0000-000000009012','BEP20',id,'APPROVED',1 from payment_methods where code='SHAM_CASH';
insert into order_financial_snapshots (internal_order_id,requested_amount,fee_percent,fee_amount,network_fee_amount,net_usdt_amount,payment_currency,local_amount,rounding_policy_version,network_config_version)
values ('00000000-0000-0000-0000-000000009022',100,10,10,0.15,89.85,'USD',100,'test',1);

insert into orders (internal_order_id,public_order_code,user_id,wallet_id,network_code,payment_method_id,status,version)
select '00000000-0000-0000-0000-000000009023','ORD-CONC-3','00000000-0000-0000-0000-000000009003','00000000-0000-0000-0000-000000009013','BEP20',id,'APPROVED',1 from payment_methods where code='SHAM_CASH';
insert into order_financial_snapshots (internal_order_id,requested_amount,fee_percent,fee_amount,network_fee_amount,net_usdt_amount,payment_currency,local_amount,rounding_policy_version,network_config_version)
values ('00000000-0000-0000-0000-000000009023',100,10,10,0.15,89.85,'USD',100,'test',1);
SQL

claim() {
  local order="$1" key="$2"
  psql_cmd -Atc "select replayed from claim_order_fulfillment('$order',1,$ADMIN,'primary','$key','$SESSION');" >/dev/null
}

confirmation() {
  local fp="$1"
  psql_cmd -Atc "select confirmation_id from create_admin_action_confirmation($ADMIN,'primary','$SESSION','fulfillment.complete','$fp');"
}

echo "1/3 same-key completion..."
claim 00000000-0000-0000-0000-000000009021 conc-claim-1
CONF=$(confirmation aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)
TX=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/a.out" 2>"$TMP_DIR/a.err" <<SQL
begin;
select internal_order_id from orders where internal_order_id='00000000-0000-0000-0000-000000009021' for update;
select pg_sleep(2);
select replayed from complete_order_fulfillment('00000000-0000-0000-0000-000000009021',2,$ADMIN,'primary','same-complete-key','$SESSION','$TX','$CONF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
commit;
SQL
) & A=$!
sleep 0.5
(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/b.out" 2>"$TMP_DIR/b.err" <<SQL
select replayed from complete_order_fulfillment('00000000-0000-0000-0000-000000009021',2,$ADMIN,'primary','same-complete-key','$SESSION','$TX','$CONF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
SQL
) & B=$!
set +e; wait $A; SA=$?; wait $B; SB=$?; set -e
test $SA -eq 0 && test $SB -eq 0
grep -Eq '^[[:space:]]*f[[:space:]]*$' "$TMP_DIR/a.out"
grep -Eq '^[[:space:]]*t[[:space:]]*$' "$TMP_DIR/b.out"
psql_cmd -c "do \$\$ begin if (select version from orders where internal_order_id='00000000-0000-0000-0000-000000009021')<>3 then raise exception 'same-key completion version mismatch'; end if; if (select count(*) from order_fulfillment_idempotency where internal_order_id='00000000-0000-0000-0000-000000009021' and operation='complete')<>1 then raise exception 'duplicate completion idempotency'; end if; if (select count(*) from audit_logs where target_id='00000000-0000-0000-0000-000000009021' and action='order.fulfillment_completed')<>1 then raise exception 'duplicate completion audit'; end if; end \$\$;"
echo "PASS: same-key completion replays safely."

echo "2/3 different-key completion..."
claim 00000000-0000-0000-0000-000000009022 conc-claim-2
CA=$(confirmation bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb)
CB=$(confirmation cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc)
(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/c.out" 2>"$TMP_DIR/c.err" <<SQL
begin;
select internal_order_id from orders where internal_order_id='00000000-0000-0000-0000-000000009022' for update;
select pg_sleep(2);
select replayed from complete_order_fulfillment('00000000-0000-0000-0000-000000009022',2,$ADMIN,'primary','different-key-a','$SESSION','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','$CA','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
commit;
SQL
) & C=$!
sleep 0.5
(
  set +e
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/d.out" 2>"$TMP_DIR/d.err" <<SQL
select replayed from complete_order_fulfillment('00000000-0000-0000-0000-000000009022',2,$ADMIN,'primary','different-key-b','$SESSION','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','$CB','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc');
SQL
  echo $? >"$TMP_DIR/d.status"
) & D=$!
wait $C; wait $D
grep -q "stale order version" "$TMP_DIR/d.err"
test "$(cat "$TMP_DIR/d.status")" -ne 0
psql_cmd -c "do \$\$ begin if (select version from orders where internal_order_id='00000000-0000-0000-0000-000000009022')<>3 then raise exception 'different-key completion version mismatch'; end if; if (select manual_usdt_transfer_reference from orders where internal_order_id='00000000-0000-0000-0000-000000009022')<>'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' then raise exception 'wrong transfer reference'; end if; end \$\$;"
echo "PASS: different-key completion serializes and rejects stale request."

echo "3/3 same-key claim..."
(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/e.out" 2>"$TMP_DIR/e.err" <<SQL
begin;
select internal_order_id from orders where internal_order_id='00000000-0000-0000-0000-000000009023' for update;
select pg_sleep(2);
select replayed from claim_order_fulfillment('00000000-0000-0000-0000-000000009023',1,$ADMIN,'primary','same-claim-key','$SESSION');
commit;
SQL
) & E=$!
sleep 0.5
(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -X -At >"$TMP_DIR/f.out" 2>"$TMP_DIR/f.err" <<SQL
select replayed from claim_order_fulfillment('00000000-0000-0000-0000-000000009023',1,$ADMIN,'primary','same-claim-key','$SESSION');
SQL
) & F=$!
set +e; wait $E; SE=$?; wait $F; SF=$?; set -e
test $SE -eq 0 && test $SF -eq 0
grep -Eq '^[[:space:]]*f[[:space:]]*$' "$TMP_DIR/e.out"
grep -Eq '^[[:space:]]*t[[:space:]]*$' "$TMP_DIR/f.out"
psql_cmd -c "do \$\$ begin if (select version from orders where internal_order_id='00000000-0000-0000-0000-000000009023')<>2 then raise exception 'same-key claim version mismatch'; end if; if (select count(*) from order_fulfillment_claims where internal_order_id='00000000-0000-0000-0000-000000009023')<>1 then raise exception 'same-key claim count mismatch'; end if; if (select count(*) from order_fulfillment_idempotency where internal_order_id='00000000-0000-0000-0000-000000009023' and operation='claim')<>1 then raise exception 'duplicate claim idempotency'; end if; end \$\$;"
echo "PASS: same-key claim replays safely."
echo "Concurrency integration tests passed."
