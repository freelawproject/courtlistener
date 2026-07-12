BEGIN;
--
-- Add field token_checksum to accesstoken
--
ALTER TABLE "oauth2_provider_accesstoken" ADD COLUMN "token_checksum" varchar(64) NULL;
--
-- Alter field token on accesstoken
--
DROP INDEX IF EXISTS "oauth2_provider_accesstoken_token_8af090f8_like";
ALTER TABLE "oauth2_provider_accesstoken" ALTER COLUMN "token" TYPE text USING "token"::text;
DROP INDEX IF EXISTS "oauth2_provider_accesstoken_token_8af090f8_like";
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL
--
-- Alter field token_checksum on accesstoken
--
ALTER TABLE "oauth2_provider_accesstoken" ALTER COLUMN "token_checksum" SET NOT NULL;
ALTER TABLE "oauth2_provider_accesstoken" ADD CONSTRAINT "oauth2_provider_accesstoken_token_checksum_85319a26_uniq" UNIQUE ("token_checksum");
CREATE INDEX "oauth2_provider_accesstoken_token_checksum_85319a26_like" ON "oauth2_provider_accesstoken" ("token_checksum" varchar_pattern_ops);
COMMIT;
