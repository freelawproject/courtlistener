BEGIN;
--
-- Create model DocketTag
--
CREATE TABLE "favorites_dockettag" ("id" serial NOT NULL PRIMARY KEY, "docket_id" integer NOT NULL);
--
-- Remove field content_type from usertag
--
SET CONSTRAINTS "favorites_usertag_content_type_id_b7337c5e_fk_django_co" IMMEDIATE; ALTER TABLE "favorites_usertag" DROP CONSTRAINT "favorites_usertag_content_type_id_b7337c5e_fk_django_co";
ALTER TABLE "favorites_usertag" DROP COLUMN "content_type_id" CASCADE;
--
-- Remove field object_id from usertag
--
ALTER TABLE "favorites_usertag" DROP COLUMN "object_id" CASCADE;
--
-- Add field tag to dockettag
--
ALTER TABLE "favorites_dockettag" ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field dockets to usertag
--
--
-- Alter unique_together for dockettag (1 constraint(s))
--
ALTER TABLE "favorites_dockettag" ADD CONSTRAINT "favorites_dockettag_docket_id_tag_id_80109530_uniq" UNIQUE ("docket_id", "tag_id");
ALTER TABLE "favorites_dockettag" ADD CONSTRAINT "favorites_dockettag_docket_id_b227f907_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "favorites_dockettag_docket_id_b227f907" ON "favorites_dockettag" ("docket_id");
CREATE INDEX "favorites_dockettag_tag_id_068a9e7e" ON "favorites_dockettag" ("tag_id");
ALTER TABLE "favorites_dockettag" ADD CONSTRAINT "favorites_dockettag_tag_id_068a9e7e_fk_favorites_usertag_id" FOREIGN KEY ("tag_id") REFERENCES "favorites_usertag" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
