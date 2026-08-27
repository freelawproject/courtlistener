BEGIN;
--
-- Add field processing_error to texasdocument
--
ALTER TABLE "search_texasdocument" ADD COLUMN "processing_error" smallint NULL;
COMMENT ON COLUMN "search_texasdocument"."processing_error" IS 'The processing error for the document, if any.';
COMMIT;
