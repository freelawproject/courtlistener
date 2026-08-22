BEGIN;
--
-- Add field token_checksum to refreshtoken
--
ALTER TABLE "oauth2_provider_refreshtoken" ADD COLUMN "token_checksum" varchar(64) NULL;
--
-- Alter unique_together for refreshtoken (0 constraint(s))
--
ALTER TABLE "oauth2_provider_refreshtoken" DROP CONSTRAINT "oauth2_provider_refreshtoken_token_revoked_af8a5134_uniq";
--
-- Alter field token on refreshtoken
--
ALTER TABLE "oauth2_provider_refreshtoken" ALTER COLUMN "token" TYPE text USING "token"::text;
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL
--
-- Alter field token_checksum on refreshtoken
--
ALTER TABLE "oauth2_provider_refreshtoken" ALTER COLUMN "token_checksum" SET NOT NULL;
--
-- Alter unique_together for refreshtoken (1 constraint(s))
--
ALTER TABLE "oauth2_provider_refreshtoken" ADD CONSTRAINT "oauth2_provider_refresht_token_checksum_revoked_46c81d1d_uniq" UNIQUE ("token_checksum", "revoked");
COMMIT;
