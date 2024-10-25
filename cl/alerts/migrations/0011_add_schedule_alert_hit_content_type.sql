BEGIN;
--
-- Add field content_type to scheduledalerthit
--
ALTER TABLE "alerts_scheduledalerthit" ADD COLUMN "content_type_id" integer NULL CONSTRAINT "alerts_scheduledaler_content_type_id_c1a4db47_fk_django_co" REFERENCES "django_content_type"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "alerts_scheduledaler_content_type_id_c1a4db47_fk_django_co" IMMEDIATE;
--
-- Add field object_id to scheduledalerthit
--
ALTER TABLE "alerts_scheduledalerthit" ADD COLUMN "object_id" integer NULL CHECK ("object_id" >= 0);
CREATE INDEX "alerts_scheduledalerthit_content_type_id_c1a4db47" ON "alerts_scheduledalerthit" ("content_type_id");
COMMIT;
