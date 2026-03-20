BEGIN;
--
-- Add field query_mode to searchquery
--
ALTER TABLE "search_searchquery" ADD COLUMN "query_mode" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "search_searchquery" ALTER COLUMN "query_mode" DROP DEFAULT;
COMMIT;
