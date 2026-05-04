BEGIN;
--
-- Add field source to apithrottle
--
ALTER TABLE "api_apithrottle" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "api_apithrottle" ALTER COLUMN "source" DROP DEFAULT;
--
-- Add field source to apithrottleevent
--
ALTER TABLE "api_apithrottleevent" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "api_apithrottleevent" ALTER COLUMN "source" DROP DEFAULT;
COMMIT;
