BEGIN;
--
-- Alter field date_created on jsonversion
--
ALTER TABLE "visualizations_jsonversion" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:49.927242+00:00'::timestamptz;
ALTER TABLE "visualizations_jsonversion" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on jsonversion
--
ALTER TABLE "visualizations_jsonversion" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:49.941065+00:00'::timestamptz;
ALTER TABLE "visualizations_jsonversion" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on referer
--
ALTER TABLE "visualizations_referer" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:49.957415+00:00'::timestamptz;
ALTER TABLE "visualizations_referer" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on referer
--
ALTER TABLE "visualizations_referer" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:49.973340+00:00'::timestamptz;
ALTER TABLE "visualizations_referer" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on scotusmap
--
ALTER TABLE "visualizations_scotusmap" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:49.999046+00:00'::timestamptz;
ALTER TABLE "visualizations_scotusmap" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on scotusmap
--
ALTER TABLE "visualizations_scotusmap" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:50.023682+00:00'::timestamptz;
ALTER TABLE "visualizations_scotusmap" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
