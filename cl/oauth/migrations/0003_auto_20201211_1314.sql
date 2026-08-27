BEGIN;
--
-- Alter field redirect_uri on grant
--
ALTER TABLE "oauth2_provider_grant" ALTER COLUMN "redirect_uri" TYPE text USING "redirect_uri"::text;
COMMIT;
