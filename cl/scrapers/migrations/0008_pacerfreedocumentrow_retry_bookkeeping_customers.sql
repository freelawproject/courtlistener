BEGIN;
--
-- Add field download_attempts to pacerfreedocumentrow
--
ALTER TABLE "scrapers_pacerfreedocumentrow" ADD COLUMN "download_attempts" integer DEFAULT 0 NOT NULL CHECK ("download_attempts" >= 0);
ALTER TABLE "scrapers_pacerfreedocumentrow" ALTER COLUMN "download_attempts" DROP DEFAULT;
--
-- Add field last_attempt to pacerfreedocumentrow
--
ALTER TABLE "scrapers_pacerfreedocumentrow" ADD COLUMN "last_attempt" timestamp with time zone NULL;
COMMIT;
