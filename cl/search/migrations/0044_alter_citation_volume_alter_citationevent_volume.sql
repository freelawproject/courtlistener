BEGIN;
--
-- Alter field volume on citation
--
ALTER TABLE "search_citation" ALTER COLUMN "volume" TYPE text USING "volume"::text;
--
-- Alter field volume on citationevent
--
ALTER TABLE "search_citationevent" ALTER COLUMN "volume" TYPE text USING "volume"::text;
COMMIT;
