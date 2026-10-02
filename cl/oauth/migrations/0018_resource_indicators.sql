BEGIN;
--
-- Add field resource to accesstoken
--
ALTER TABLE "oauth2_provider_accesstoken" ADD COLUMN "resource" jsonb DEFAULT '[]'::jsonb NOT NULL;
ALTER TABLE "oauth2_provider_accesstoken" ALTER COLUMN "resource" DROP DEFAULT;
--
-- Add field resource to grant
--
ALTER TABLE "oauth2_provider_grant" ADD COLUMN "resource" jsonb DEFAULT '[]'::jsonb NOT NULL;
ALTER TABLE "oauth2_provider_grant" ALTER COLUMN "resource" DROP DEFAULT;
--
-- Add field resource to refreshtoken
--
ALTER TABLE "oauth2_provider_refreshtoken" ADD COLUMN "resource" jsonb DEFAULT '[]'::jsonb NOT NULL;
ALTER TABLE "oauth2_provider_refreshtoken" ALTER COLUMN "resource" DROP DEFAULT;
COMMIT;
