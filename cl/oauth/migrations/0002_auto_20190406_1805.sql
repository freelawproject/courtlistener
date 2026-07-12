BEGIN;
--
-- Add field code_challenge to grant
--
ALTER TABLE "oauth2_provider_grant" ADD COLUMN "code_challenge" varchar(128) DEFAULT '' NOT NULL;
ALTER TABLE "oauth2_provider_grant" ALTER COLUMN "code_challenge" DROP DEFAULT;
--
-- Add field code_challenge_method to grant
--
ALTER TABLE "oauth2_provider_grant" ADD COLUMN "code_challenge_method" varchar(10) DEFAULT '' NOT NULL;
ALTER TABLE "oauth2_provider_grant" ALTER COLUMN "code_challenge_method" DROP DEFAULT;
COMMIT;
