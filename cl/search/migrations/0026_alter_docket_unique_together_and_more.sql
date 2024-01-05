--
-- Drop the unique_together constraint for dockets
--
ALTER TABLE "search_docket" DROP CONSTRAINT "search_docket_docket_number_7642c6c6dbd04704_uniq";
--
-- Drop the index on the docket_number field
--
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_docket_number_4af29e98dca38326_uniq";
