BEGIN;
--
-- Add field main_version to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "main_version_id" integer NULL CONSTRAINT "search_opinion_main_version_id_6d958799_fk_search_opinion_id" REFERENCES "search_opinion"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_opinion_main_version_id_6d958799_fk_search_opinion_id" IMMEDIATE;
--
-- Add field main_version to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "main_version_id" integer NULL;

CREATE INDEX "search_opinion_main_version_id_6d958799" ON "search_opinion" ("main_version_id");
CREATE INDEX "search_opinionevent_main_version_id_072bff05" ON "search_opinionevent" ("main_version_id");
COMMIT;
