-- Al-Manara v2 — distinguish customer and admin audit actors
-- Customer actions must not be encoded as admin actor types.

alter table audit_logs
  add column actor_kind text;

update audit_logs
set actor_kind = case
  when actor_telegram_user_id is null then null
  else 'admin'
end
where actor_kind is null;

alter table audit_logs
  add constraint audit_actor_kind_valid
  check (actor_kind is null or actor_kind in ('customer','admin'));

alter table audit_logs
  drop constraint audit_actor_type_pair;

alter table audit_logs
  add constraint audit_actor_contract
  check (
    actor_telegram_user_id is null
    or (
      actor_kind = 'admin'
      and actor_type is not null
    )
    or (
      actor_kind = 'customer'
      and actor_type is null
    )
  );

create index audit_logs_actor_kind_idx
  on audit_logs(actor_kind, created_at desc);

comment on column audit_logs.actor_kind is
  'Actor class: admin or customer. Null denotes a system/background event.';
