BEGIN;
--
-- Add field joined_by_str to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "joined_by_str" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "joined_by_str" DROP DEFAULT;
--
-- Add field xml_harvard to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "xml_harvard" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "xml_harvard" DROP DEFAULT;
--
-- Add field correction to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "correction" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "correction" DROP DEFAULT;
--
-- Add field cross_reference to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "cross_reference" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "cross_reference" DROP DEFAULT;
--
-- Add field disposition to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "disposition" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "disposition" DROP DEFAULT;
--
-- Add field filepath_json_harvard to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "filepath_json_harvard" varchar(1000) DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "filepath_json_harvard" DROP DEFAULT;
--
-- Add field headnotes to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "headnotes" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "headnotes" DROP DEFAULT;
--
-- Add field history to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "history" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "history" DROP DEFAULT;
--
-- Add field other_dates to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "other_dates" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "other_dates" DROP DEFAULT;
--
-- Add field summary to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "summary" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "summary" DROP DEFAULT;
--
-- Alter field claim on claimhistory
--
SET CONSTRAINTS "search_claimhistory_claim_id_e130e572_fk_search_claim_id" IMMEDIATE; ALTER TABLE "search_claimhistory" DROP CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id";
ALTER TABLE "search_claimhistory" ADD CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
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
