BEGIN;
--
-- Add field processing_error to texasdocument
--
ALTER TABLE "search_texasdocument" ADD COLUMN "processing_error" smallint NULL;
COMMENT ON COLUMN "search_texasdocument"."processing_error" IS 'The processing error for the document, if any.';
--
-- Add field processing_error to texasdocumentevent
--
ALTER TABLE "search_texasdocumentevent" ADD COLUMN "processing_error" smallint NULL;
COMMENT ON COLUMN "search_texasdocumentevent"."processing_error" IS 'The processing error for the document, if any.';
COMMIT;
