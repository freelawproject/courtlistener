--
-- Raw SQL operation
--
CREATE UNIQUE INDEX CONCURRENTLY "unique_note_per_user_per_object" ON "favorites_note" ("content_type_id", "object_id", "user_id") WHERE "content_type_id" IS NOT NULL;
