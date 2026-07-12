BEGIN;
--
-- Add field hash_client_secret to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "hash_client_secret" boolean DEFAULT true NOT NULL;
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "hash_client_secret" DROP DEFAULT;
COMMIT;
