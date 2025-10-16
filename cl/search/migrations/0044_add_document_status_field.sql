
BEGIN;
--
-- Add field document_status to recapdocument
--
ALTER TABLE "search_recapdocument" ADD COLUMN "document_status" text DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocument" ALTER COLUMN "document_status" DROP DEFAULT;
--
-- Add field document_status to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent" ADD COLUMN "document_status" text DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocumentevent" ALTER COLUMN "document_status" DROP DEFAULT;
COMMIT;