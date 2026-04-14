BEGIN;
--
-- Add field object_ids to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "object_ids" jsonb DEFAULT '[]'::jsonb NOT NULL;
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "object_ids" DROP DEFAULT;
--
-- Add field related_model to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "related_model_id" integer NULL CONSTRAINT "recap_emailprocessin_related_model_id_2d7c8956_fk_django_co" REFERENCES "django_content_type"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "recap_emailprocessin_related_model_id_2d7c8956_fk_django_co" IMMEDIATE;
--
-- Add field source to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "source" DROP DEFAULT;
CREATE INDEX "recap_emailprocessingqueue_related_model_id_2d7c8956" ON "recap_emailprocessingqueue" ("related_model_id");
COMMIT;
