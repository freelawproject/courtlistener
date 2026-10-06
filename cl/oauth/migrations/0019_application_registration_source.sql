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
-- The Python step copies dcr_created=true rows to registration_source='dcr'.
-- dcr_created was never populated here (it was added and removed in the same
-- upgrade), so it touches no rows.
--
-- Remove field dcr_created from application
--
ALTER TABLE "oauth2_provider_application" DROP COLUMN "dcr_created";
COMMIT;
