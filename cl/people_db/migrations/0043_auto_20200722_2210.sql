-- Migration: Safe.


BEGIN;
--
-- Add field date_completed to person
--
ALTER TABLE "people_db_person" ADD COLUMN "date_completed" timestamp with time zone NULL;
--
-- Add field dob_country to person
--
ALTER TABLE "people_db_person" ADD COLUMN "dob_country" varchar(50) DEFAULT 'United States' NOT NULL;
ALTER TABLE "people_db_person" ALTER COLUMN "dob_country" DROP DEFAULT;
--
-- Add field dod_country to person
--
ALTER TABLE "people_db_person" ADD COLUMN "dod_country" varchar(50) DEFAULT 'United States' NOT NULL;
ALTER TABLE "people_db_person" ALTER COLUMN "dod_country" DROP DEFAULT;
--
-- Add field sector to position
--
ALTER TABLE "people_db_position" ADD COLUMN "sector" smallint NULL;
--
-- Alter field extra_info on party
--
--
-- Alter field date_start on position
--
ALTER TABLE "people_db_position" ALTER COLUMN "date_start" DROP NOT NULL;
--
-- Alter field position_type on position
--
COMMIT;
