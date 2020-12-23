BEGIN;
--
-- Alter field date_created on fjcintegrateddatabase
--
ALTER TABLE "recap_fjcintegrateddatabase" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:00.161323+00:00'::timestamptz;
ALTER TABLE "recap_fjcintegrateddatabase" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on fjcintegrateddatabase
--
ALTER TABLE "recap_fjcintegrateddatabase" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:00.182602+00:00'::timestamptz;
ALTER TABLE "recap_fjcintegrateddatabase" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on pacerfetchqueue
--
ALTER TABLE "recap_pacerfetchqueue" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:00.225029+00:00'::timestamptz;
ALTER TABLE "recap_pacerfetchqueue" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on pacerfetchqueue
--
ALTER TABLE "recap_pacerfetchqueue" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:00.267766+00:00'::timestamptz;
ALTER TABLE "recap_pacerfetchqueue" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on pacerhtmlfiles
--
ALTER TABLE "recap_pacerhtmlfiles" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:00.274867+00:00'::timestamptz;
ALTER TABLE "recap_pacerhtmlfiles" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on pacerhtmlfiles
--
ALTER TABLE "recap_pacerhtmlfiles" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:00.280415+00:00'::timestamptz;
ALTER TABLE "recap_pacerhtmlfiles" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on processingqueue
--
ALTER TABLE "recap_processingqueue" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:00.323179+00:00'::timestamptz;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on processingqueue
--
ALTER TABLE "recap_processingqueue" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:00.363627+00:00'::timestamptz;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
