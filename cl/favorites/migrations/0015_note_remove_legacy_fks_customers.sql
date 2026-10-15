--
-- Make content_type/object_id required
--
ALTER TABLE "favorites_note" ALTER COLUMN "content_type_id" SET NOT NULL, ALTER COLUMN "object_id" SET NOT NULL;
--
-- Swap the partial unique index for a full unique constraint
--
CREATE UNIQUE INDEX CONCURRENTLY "unique_note_per_user_per_object_new" ON "favorites_note" ("content_type_id", "object_id", "user_id");
DROP INDEX CONCURRENTLY IF EXISTS "unique_note_per_user_per_object";
ALTER TABLE "favorites_note" ADD CONSTRAINT "unique_note_per_user_per_object" UNIQUE USING INDEX "unique_note_per_user_per_object_new";
--
-- Remove the legacy per-type FKs from note (also drops their FK, index and
-- unique_together constraints)
--
ALTER TABLE "favorites_note" DROP COLUMN "audio_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "cluster_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "docket_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "recap_doc_id_id";
