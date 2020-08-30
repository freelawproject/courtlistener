-- Migration: Safe.

BEGIN;
--
-- Create model Note
--
CREATE TABLE "lib_note" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_entered" timestamp with time zone NOT NULL, "notes" text NOT NULL, "object_id" integer NOT NULL CHECK ("object_id" >= 0), "content_type_id" integer NOT NULL);
ALTER TABLE "lib_note" ADD CONSTRAINT "lib_note_content_type_id_a36a71d5_fk_django_content_type_id" FOREIGN KEY ("content_type_id") REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lib_note_date_created_7cf4d151" ON "lib_note" ("date_created");
CREATE INDEX "lib_note_date_modified_19d0820a" ON "lib_note" ("date_modified");
CREATE INDEX "lib_note_content_type_id_a36a71d5" ON "lib_note" ("content_type_id");
COMMIT;
