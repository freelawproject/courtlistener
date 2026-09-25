BEGIN;
--
-- Add field content_type to note
--
ALTER TABLE "favorites_note" ADD COLUMN "content_type_id" integer NULL CONSTRAINT "favorites_note_content_type_id_a1aab4c0_fk_django_co" REFERENCES "django_content_type"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "favorites_note_content_type_id_a1aab4c0_fk_django_co" IMMEDIATE;
--
-- Add field object_id to note
--
ALTER TABLE "favorites_note" ADD COLUMN "object_id" integer NULL CHECK ("object_id" >= 0);
--
-- Custom state/database change combination
--
ALTER TABLE "favorites_noteevent" ADD COLUMN "content_type_id" integer NULL;
--
-- Add field object_id to noteevent
--
ALTER TABLE "favorites_noteevent" ADD COLUMN "object_id" integer NULL CHECK ("object_id" >= 0);
COMMIT;
