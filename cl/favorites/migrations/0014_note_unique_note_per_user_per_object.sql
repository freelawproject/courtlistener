--
-- Raw SQL operation
--
CREATE UNIQUE INDEX CONCURRENTLY "unique_note_per_user_per_object" ON "favorites_note" ("content_type_id", "object_id", "user_id") WHERE "content_type_id" IS NOT NULL;
--
-- Raw SQL operation
--
CREATE INDEX CONCURRENTLY "favorites_noteevent_content_type_id_16687302" ON "favorites_noteevent" ("content_type_id");
