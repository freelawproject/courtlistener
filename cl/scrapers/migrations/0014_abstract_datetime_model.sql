BEGIN;
--
-- Alter field date_created on pacermobilepagedata
--
ALTER TABLE "scrapers_pacermobilepagedata" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:07:23.385751+00:00'::timestamptz;
ALTER TABLE "scrapers_pacermobilepagedata" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on pacermobilepagedata
--
ALTER TABLE "scrapers_pacermobilepagedata" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:07:23.421493+00:00'::timestamptz;
ALTER TABLE "scrapers_pacermobilepagedata" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
