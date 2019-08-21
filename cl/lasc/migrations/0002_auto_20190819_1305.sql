BEGIN;
--
-- Alter field date_modified on docket
--
ALTER TABLE "lasc_docket" ALTER COLUMN "date_modified" SET DEFAULT '2019-08-20T15:50:37.641935+00:00'::timestamptz;
ALTER TABLE "lasc_docket" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
