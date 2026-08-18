BEGIN;
--
-- Add field parsed_document_count to pacerfreedocumentlog
--
-- PERF: Adding a nullable column with no default is a metadata-only change.
-- No table rewrite, no long lock. Instantaneous. The CHECK constraint is
-- cheap here too: the column is brand new, so every row is NULL and there is
-- nothing to scan.
ALTER TABLE "scrapers_pacerfreedocumentlog" ADD COLUMN "parsed_document_count" integer NULL CHECK ("parsed_document_count" >= 0);
--
-- Add field reported_document_count to pacerfreedocumentlog
--
-- PERF: Same as above. Metadata-only.
ALTER TABLE "scrapers_pacerfreedocumentlog" ADD COLUMN "reported_document_count" integer NULL CHECK ("reported_document_count" >= 0);
--
-- Add field saved_document_count to pacerfreedocumentlog
--
-- PERF: Same as above. Metadata-only.
ALTER TABLE "scrapers_pacerfreedocumentlog" ADD COLUMN "saved_document_count" integer NULL CHECK ("saved_document_count" >= 0);
COMMIT;
