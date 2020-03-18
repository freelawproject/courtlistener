--
-- This SQL was tweaked by hand to avoid setting DEFAULT on columns. See issue
-- #1106 for details on why that's bad.
--
-- It was further modified to convert it to three transactions. One for adding
-- columns, one for updating them, and the third for making the columns not
-- null.
BEGIN;
--
-- Add field joined_by_str to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "joined_by_str" text;
--
-- Add field xml_harvard to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "xml_harvard" text;
--
-- Add field correction to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "correction" text;
--
-- Add field cross_reference to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "cross_reference" text;
--
-- Add field disposition to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "disposition" text;
--
-- Add field filepath_json_harvard to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "filepath_json_harvard" varchar(1000);
--
-- Add field headnotes to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "headnotes" text;
--
-- Add field history to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "history" text;
--
-- Add field other_dates to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "other_dates" text;
--
-- Add field summary to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "summary" text;

--
-- Alter field source on docket
--
--
-- Alter field html on opinion
--
ALTER TABLE "search_opinion" ALTER COLUMN "html" SET DEFAULT '';
UPDATE "search_opinion" SET "html" = '' WHERE "html" IS NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html" SET NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html" DROP DEFAULT;
--
-- Alter field html_columbia on opinion
--
ALTER TABLE "search_opinion" ALTER COLUMN "html_columbia" SET DEFAULT '';
UPDATE "search_opinion" SET "html_columbia" = '' WHERE "html_columbia" IS NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html_columbia" SET NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html_columbia" DROP DEFAULT;
--
-- Alter field html_lawbox on opinion
--
ALTER TABLE "search_opinion" ALTER COLUMN "html_lawbox" SET DEFAULT '';
UPDATE "search_opinion" SET "html_lawbox" = '' WHERE "html_lawbox" IS NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html_lawbox" SET NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html_lawbox" DROP DEFAULT;
--
-- Alter field type on opinion
--
--
-- Alter field source on opinioncluster
--
COMMIT;

--
-- Set all new columns to blank instead of NULL
--
BEGIN;
UPDATE "search_opinion" set "joined_by_str" = '' WHERE "joined_by_str" IS NULL;
UPDATE "search_opinion" set "xml_harvard" = '' WHERE "xml_harvard" IS NULL;
UPDATE "search_opinioncluster" set "correction" = '' WHERE "correction" IS NULL;
UPDATE "search_opinioncluster" set "cross_reference" = '' WHERE "cross_reference" IS NULL;
UPDATE "search_opinioncluster" set "disposition" = '' WHERE "disposition" IS NULL;
UPDATE "search_opinioncluster" set "filepath_json_harvard" = '' WHERE "filepath_json_harvard" IS NULL;
UPDATE "search_opinioncluster" set "headnotes" = '' WHERE "headnotes" IS NULL;
UPDATE "search_opinioncluster" set "history" = '' WHERE "history" IS NULL;
UPDATE "search_opinioncluster" set "other_dates" = '' WHERE "other_dates" IS NULL;
UPDATE "search_opinioncluster" set "summary" = '' WHERE "summary" IS NULL;
COMMIT;

--
-- Finally, make the columns NOT NULL
--
BEGIN;
ALTER TABLE "search_opinion" ALTER COLUMN "joined_by_str" SET NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "xml_harvard" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "correction" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "cross_reference" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "disposition" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "filepath_json_harvard" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "headnotes" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "history" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "other_dates" SET NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "summary" SET NOT NULL;
COMMIT;
