BEGIN;
--
-- Alter field date_created on abarating
--
ALTER TABLE "people_db_abarating" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.335211+00:00'::timestamptz;
ALTER TABLE "people_db_abarating" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on abarating
--
ALTER TABLE "people_db_abarating" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.368522+00:00'::timestamptz;
ALTER TABLE "people_db_abarating" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on attorney
--
ALTER TABLE "people_db_attorney" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.378694+00:00'::timestamptz;
ALTER TABLE "people_db_attorney" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on attorney
--
ALTER TABLE "people_db_attorney" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.389280+00:00'::timestamptz;
ALTER TABLE "people_db_attorney" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on attorneyorganization
--
ALTER TABLE "people_db_attorneyorganization" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.403718+00:00'::timestamptz;
ALTER TABLE "people_db_attorneyorganization" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on attorneyorganization
--
ALTER TABLE "people_db_attorneyorganization" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.414833+00:00'::timestamptz;
ALTER TABLE "people_db_attorneyorganization" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on education
--
ALTER TABLE "people_db_education" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.454063+00:00'::timestamptz;
ALTER TABLE "people_db_education" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on education
--
ALTER TABLE "people_db_education" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.483633+00:00'::timestamptz;
ALTER TABLE "people_db_education" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on party
--
ALTER TABLE "people_db_party" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.496514+00:00'::timestamptz;
ALTER TABLE "people_db_party" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on party
--
ALTER TABLE "people_db_party" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.516617+00:00'::timestamptz;
ALTER TABLE "people_db_party" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on person
--
ALTER TABLE "people_db_person" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.571482+00:00'::timestamptz;
ALTER TABLE "people_db_person" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on person
--
ALTER TABLE "people_db_person" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.602564+00:00'::timestamptz;
ALTER TABLE "people_db_person" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on politicalaffiliation
--
ALTER TABLE "people_db_politicalaffiliation" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.635065+00:00'::timestamptz;
ALTER TABLE "people_db_politicalaffiliation" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on politicalaffiliation
--
ALTER TABLE "people_db_politicalaffiliation" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.669332+00:00'::timestamptz;
ALTER TABLE "people_db_politicalaffiliation" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on position
--
ALTER TABLE "people_db_position" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.712106+00:00'::timestamptz;
ALTER TABLE "people_db_position" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on position
--
ALTER TABLE "people_db_position" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.748204+00:00'::timestamptz;
ALTER TABLE "people_db_position" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on retentionevent
--
ALTER TABLE "people_db_retentionevent" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.774514+00:00'::timestamptz;
ALTER TABLE "people_db_retentionevent" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on retentionevent
--
ALTER TABLE "people_db_retentionevent" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.801204+00:00'::timestamptz;
ALTER TABLE "people_db_retentionevent" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on school
--
ALTER TABLE "people_db_school" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.815125+00:00'::timestamptz;
ALTER TABLE "people_db_school" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on school
--
ALTER TABLE "people_db_school" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.835655+00:00'::timestamptz;
ALTER TABLE "people_db_school" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on source
--
ALTER TABLE "people_db_source" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:04:33.877124+00:00'::timestamptz;
ALTER TABLE "people_db_source" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on source
--
ALTER TABLE "people_db_source" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:04:33.932948+00:00'::timestamptz;
ALTER TABLE "people_db_source" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
