begin;

select plan(3);

select has_index(
    'public',
    'orders',
    'orders_one_active_per_user_uq',
    'orders enforce a unique active order per customer'
);

select is(
    (
        select pg_get_expr(i.indpred, i.indrelid)
          from pg_index i
          join pg_class c on c.oid = i.indexrelid
          join pg_class t on t.oid = i.indrelid
         where t.relname = 'orders'
           and c.relname = 'orders_one_active_per_user_uq'
    ),
    '(status = ANY (ARRAY[''DRAFT''::order_status, ''PENDING_PAYMENT''::order_status, ''PAYMENT_SUBMITTED''::order_status, ''UNDER_REVIEW''::order_status, ''APPROVED''::order_status, ''CLARIFICATION_REQUIRED''::order_status]))',
    'only non-terminal customer order states participate in the uniqueness guard'
);

select ok(
    not exists (
        select 1
          from pg_index i
          join pg_class c on c.oid = i.indexrelid
         where c.relname = 'orders_one_active_per_user_uq'
           and i.indisvalid = false
    ),
    'single active order index is valid'
);

select * from finish();
rollback;
