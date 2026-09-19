-- Add the sixth operational network type in its own migration.
-- PostgreSQL must commit a newly-added enum label before it can be used by
-- subsequent DML in a separate migration transaction.
alter type network_code add value if not exists 'POLYGON';
