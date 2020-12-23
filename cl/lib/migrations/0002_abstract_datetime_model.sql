BEGIN;
--
-- Alter field date_created on note
--
ALTER TABLE "lib_note" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:03:19.681465+00:00'::timestamptz;
ALTER TABLE "lib_note" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on note
--
ALTER TABLE "lib_note" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:03:19.685201+00:00'::timestamptz;
ALTER TABLE "lib_note" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
