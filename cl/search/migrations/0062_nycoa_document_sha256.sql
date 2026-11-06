BEGIN;
--
-- Add field sha256 to nycoadocument
--
ALTER TABLE "search_nycoadocument" ADD COLUMN "sha256" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_nycoadocument" ALTER COLUMN "sha256" DROP DEFAULT;
COMMENT ON COLUMN "search_nycoadocument"."sha256" IS 'Hex digest of the file.';
--
-- Add field sha256 to nycoadocumentevent
--
ALTER TABLE "search_nycoadocumentevent" ADD COLUMN "sha256" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_nycoadocumentevent" ALTER COLUMN "sha256" DROP DEFAULT;
COMMENT ON COLUMN "search_nycoadocumentevent"."sha256" IS 'Hex digest of the file.';
COMMIT;
