BEGIN;
--
-- Add field date_created to citation
--
ALTER TABLE "search_citation" ADD COLUMN "date_created" timestamp with time zone DEFAULT '2025-08-20 22:12:45.747808+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citation" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Add field date_modified to citation
--
ALTER TABLE "search_citation" ADD COLUMN "date_modified" timestamp with time zone DEFAULT '2025-08-20 22:12:45.770243+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citation" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field volume on citation
--
ALTER TABLE "search_citation" ALTER COLUMN "volume" TYPE text USING "volume"::text;
COMMIT;
