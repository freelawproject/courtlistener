BEGIN;
--
-- Add field main_version to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "main_version_id" integer NULL CONSTRAINT "search_opinion_main_version_id_6d958799_fk_search_opinion_id" REFERENCES "search_opinion"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_opinion_main_version_id_6d958799_fk_search_opinion_id" IMMEDIATE;
CREATE INDEX "search_opinion_main_version_id_6d958799" ON "search_opinion" ("main_version_id");
COMMIT;
