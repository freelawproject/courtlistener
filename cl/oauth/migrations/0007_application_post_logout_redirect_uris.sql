BEGIN;
--
-- Add field post_logout_redirect_uris to application
--
ALTER TABLE "oauth2_provider_application" ADD COLUMN "post_logout_redirect_uris" text DEFAULT '' NOT NULL;
ALTER TABLE "oauth2_provider_application" ALTER COLUMN "post_logout_redirect_uris" DROP DEFAULT;
COMMIT;
