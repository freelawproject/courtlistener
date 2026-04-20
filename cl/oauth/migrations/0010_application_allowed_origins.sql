BEGIN;
--
-- Add field allowed_origins to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "allowed_origins" text DEFAULT '' NOT NULL;
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "allowed_origins" DROP DEFAULT;
COMMIT;
