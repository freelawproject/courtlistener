BEGIN;
--
-- Add field sha256 to nycoadocument
--
ALTER TABLE "search_nycoadocument" ADD COLUMN "sha256" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_nycoadocument" ALTER COLUMN "sha256" DROP DEFAULT;
COMMENT ON COLUMN "search_nycoadocument"."sha256" IS 'Hex digest of the file, as the scraper hashed it on the way to storage. Empty for a file no scrape has fetched. This is what tells a file the Court has corrected from the one already published, and the inherited `sha1` stays empty in its favour, because nothing on this model''s path ever reads the bytes; see `make_filename`.';
COMMIT;
