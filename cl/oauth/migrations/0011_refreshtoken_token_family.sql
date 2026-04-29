BEGIN;
--
-- Add field token_family to refreshtoken
--
ALTER TABLE "oauth2_provider_refreshtoken" ADD COLUMN "token_family" uuid NULL;
COMMIT;
