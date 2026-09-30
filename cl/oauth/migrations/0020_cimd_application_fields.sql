BEGIN;
--
-- Add field cimd_expires_at to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "cimd_expires_at" timestamp with time zone NULL;
--
-- Alter field client_id on application
--
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "client_id" TYPE varchar(255);
COMMIT;
