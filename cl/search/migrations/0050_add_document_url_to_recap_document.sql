BEGIN;
--
-- Add field document_url to recapdocument
--
ALTER TABLE "search_recapdocument" ADD COLUMN "document_url" varchar(1000) DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocument" ALTER COLUMN "document_url" DROP DEFAULT;
--
-- Add field document_url to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent" ADD COLUMN "document_url" varchar(1000) DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocumentevent" ALTER COLUMN "document_url" DROP DEFAULT;

COMMIT;
