BEGIN;
--
-- Add field dcr_created to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "dcr_created" boolean DEFAULT false NOT NULL;
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "dcr_created" DROP DEFAULT;
COMMIT;
