BEGIN;
--
-- Add field processing_state to texasdocument
--
ALTER TABLE "search_texasdocument" ADD COLUMN "processing_state" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "search_texasdocument" ALTER COLUMN "processing_state" DROP DEFAULT;
COMMENT ON COLUMN "search_texasdocument"."processing_state" IS 'The processing state of the document.';
--
-- Backfill processing_state for existing rows
--
UPDATE "search_texasdocument"
SET "processing_state" = CASE
    WHEN "plain_text" != '' THEN 3   -- SUMMARIZED
    WHEN "filepath_local" != '' THEN 1 -- DOWNLOADED
    ELSE 0                             -- PENDING
END
WHERE "filepath_local" != '' OR "plain_text" != '';
COMMIT;