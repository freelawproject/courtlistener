BEGIN;
--
-- Add field html_harvard to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "html_harvard" text NULL;
--
-- Add field joined_by_str to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "joined_by_str" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "joined_by_str" DROP DEFAULT;
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
-- Add field filepath_local to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "filepath_local" varchar(1000) DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "filepath_local" DROP DEFAULT;
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
-- Add field html_harvard to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "html_harvard" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "html_harvard" DROP DEFAULT;
--
-- Add field image_missing to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "image_missing" boolean DEFAULT false NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "image_missing" DROP DEFAULT;
--
-- Add field other_date to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "other_date" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "other_date" DROP DEFAULT;
--
-- Add field page_count to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "page_count" integer NULL;
--
-- Add field sha1 to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "sha1" varchar(40) DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "sha1" DROP DEFAULT;
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
-- Alter field type on opinion
--
--
-- Alter field source on opinioncluster
--
CREATE INDEX "search_opinioncluster_image_missing_55ffb4ef" ON "search_opinioncluster" ("image_missing");
CREATE INDEX "search_opinioncluster_sha1_00b4d27d" ON "search_opinioncluster" ("sha1");
CREATE INDEX "search_opinioncluster_sha1_00b4d27d_like" ON "search_opinioncluster" ("sha1" varchar_pattern_ops);
COMMIT;
