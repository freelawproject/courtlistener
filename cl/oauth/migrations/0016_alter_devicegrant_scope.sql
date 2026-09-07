BEGIN;
--
-- Alter field scope on devicegrant
--
ALTER TABLE "oauth2_provider_devicegrant" ALTER COLUMN "scope" TYPE text USING "scope"::text, ALTER COLUMN "scope" SET DEFAULT '';
UPDATE "oauth2_provider_devicegrant" SET "scope" = '' WHERE "scope" IS NULL; SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE "oauth2_provider_devicegrant" ALTER COLUMN "scope" SET NOT NULL;
ALTER TABLE "oauth2_provider_devicegrant" ALTER COLUMN "scope" DROP DEFAULT;
COMMIT;
