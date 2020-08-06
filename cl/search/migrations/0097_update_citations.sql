BEGIN;
--
-- Add field raw to citation
--
ALTER TABLE "search_citation" ADD COLUMN "raw" text DEFAULT '' NOT NULL;
ALTER TABLE "search_citation" ALTER COLUMN "raw" DROP DEFAULT;
--
-- Alter field volume on citation
--
ALTER TABLE "search_citation" ALTER COLUMN "volume" TYPE text USING "volume"::text, ALTER COLUMN "volume" DROP NOT NULL;
--
-- Alter field source on opinioncluster
--
COMMIT;
