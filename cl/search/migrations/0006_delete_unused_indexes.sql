-- A few things here:
-- 1. The index names here are generated by Django 3.1, which uses different
--    names for the indexes. As a result, you have to get them from the DB and
--    use those.
-- 2. When you add the CONCURRENTLY keyword, you can't do it in a transaction
--    anymore, so remove the transaction.

--
-- Alter field date_argued on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_220746bf";
--
-- Alter field date_cert_denied on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_40a9d293";
--
-- Alter field date_cert_granted on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_70bec8bd";
--
-- Alter field date_reargued on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_dc3f2df2";
--
-- Alter field date_reargument_denied on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_657961a4";
--
-- Alter field ia_date_first_change on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_4f3b580f";
--
-- Alter index_together for docket (0 constraint(s))
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_ia_upload_failure_count_28fe663d91d7ffbb_idx";
