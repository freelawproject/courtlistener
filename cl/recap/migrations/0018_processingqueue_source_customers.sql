BEGIN;
--
-- Add field source to processingqueue
--
ALTER TABLE "recap_processingqueue" ADD COLUMN "source" smallint DEFAULT 4 NOT NULL;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "source" DROP DEFAULT;
COMMIT;
