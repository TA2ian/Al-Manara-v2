-- Harden PL/pgSQL UPDATE statements against output-parameter/column ambiguity.
-- The affected functions return a column named internal_order_id, which can
-- collide with the orders table column under strict database linting.

DO $$
declare
    v_function oid;
    v_definition text;
begin
    foreach v_function in array ARRAY[
        to_regprocedure('public.transition_order_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,jsonb,text)'),
        to_regprocedure('public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)'),
        to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)')
    ]::oid[] loop
        if v_function is null then
            raise exception 'required order function is missing';
        end if;

        select pg_get_functiondef(v_function) into v_definition;

        v_definition := replace(
            v_definition,
            'update orders\n       set',
            'update orders as o\n       set'
        );
        v_definition := replace(
            v_definition,
            'where internal_order_id = p_order_id',
            'where o.internal_order_id = p_order_id'
        );

        execute v_definition;
    end loop;
end
$$;
