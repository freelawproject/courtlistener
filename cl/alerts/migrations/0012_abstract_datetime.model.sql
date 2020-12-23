BEGIN;
--
-- Alter field date_created on alert
--
ALTER TABLE "alerts_alert" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T14:59:08.294113+00:00'::timestamptz;
ALTER TABLE "alerts_alert" ALTER COLUMN "date_created" DROP DEFAULT;
COMMIT;
