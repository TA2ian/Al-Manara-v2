begin;
select plan(1);
select ok((select count(*) from pg_proc where proname='enforce_receipt_attempt_limit')=1,'receipt attempt allocator exists');
select * from finish();
rollback;
