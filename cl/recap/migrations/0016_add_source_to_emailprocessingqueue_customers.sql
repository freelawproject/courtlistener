BEGIN;
--
-- Add field source to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "source" DROP DEFAULT;
COMMIT;
