BEGIN;
--
-- Add field document_count to pacerfreedocumentlog
--
-- PERF: Adding a nullable column with no default is a metadata-only change.
-- No table rewrite, no long lock. Instantaneous.
ALTER TABLE "scrapers_pacerfreedocumentlog" ADD COLUMN "document_count" integer NULL;
COMMIT;
