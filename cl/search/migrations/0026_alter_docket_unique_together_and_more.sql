--
-- Alter unique_together for docket (0 constraint(s))
--
ALTER TABLE "search_docket" DROP CONSTRAINT "search_docket_docket_number_pacer_case_a3184727_uniq";
--
-- Alter field docket_number on docket
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_docket_number_b2afb9d6";
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_docket_number_b2afb9d6_like";
