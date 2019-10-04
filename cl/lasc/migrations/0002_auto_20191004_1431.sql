BEGIN;
--
-- Change Meta options on action
--
--
-- Change Meta options on lascjson
--
--
-- Remove field filepath from lascpdf
--
ALTER TABLE "lasc_lascpdf" DROP COLUMN "filepath" CASCADE;
--
-- Add field filepath_s3 to lascpdf
--
ALTER TABLE "lasc_lascpdf" ADD COLUMN "filepath_s3" varchar(150) DEFAULT '' NOT NULL;
ALTER TABLE "lasc_lascpdf" ALTER COLUMN "filepath_s3" DROP DEFAULT;
--
-- Alter field filepath on lascjson
--
COMMIT;
