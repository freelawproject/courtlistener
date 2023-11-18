BEGIN;
--
-- Alter field document_number on processingqueue
--
ALTER TABLE "recap_processingqueue" ALTER COLUMN "document_number" TYPE varchar(32) USING "document_number"::varchar(32), ALTER COLUMN "document_number" SET DEFAULT '';
UPDATE "recap_processingqueue" SET "document_number" = '' WHERE "document_number" IS NULL; SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "document_number" SET NOT NULL;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "document_number" DROP DEFAULT;
COMMIT;
