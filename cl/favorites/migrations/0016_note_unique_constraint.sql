--
-- Swap the partial unique index for a full unique constraint
--
CREATE UNIQUE INDEX CONCURRENTLY "unique_note_per_user_per_object_new" ON "favorites_note" ("content_type_id", "object_id", "user_id");
DROP INDEX CONCURRENTLY IF EXISTS "unique_note_per_user_per_object";
ALTER TABLE "favorites_note" ADD CONSTRAINT "unique_note_per_user_per_object" UNIQUE USING INDEX "unique_note_per_user_per_object_new";
