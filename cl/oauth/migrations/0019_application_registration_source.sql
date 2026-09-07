BEGIN;
--
-- Add field registration_source to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "registration_source" varchar(32) DEFAULT 'manual' NOT NULL;
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "registration_source" DROP DEFAULT;
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL
--
-- Remove field dcr_created from application
--
ALTER TABLE "oauth2_provider_application" DROP COLUMN "dcr_created";
COMMIT;
