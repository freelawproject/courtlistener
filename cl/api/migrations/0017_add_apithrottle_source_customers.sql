BEGIN;
--
-- Add field source to apithrottle
--
ALTER TABLE "api_apithrottle" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "api_apithrottle" ALTER COLUMN "source" DROP DEFAULT;
COMMIT;
