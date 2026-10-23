BEGIN;
--
-- Make content_type/object_id required
--
ALTER TABLE "favorites_note" ALTER COLUMN "content_type_id" SET NOT NULL, ALTER COLUMN "object_id" SET NOT NULL;
ALTER TABLE "favorites_noteevent" ALTER COLUMN "content_type_id" SET NOT NULL, ALTER COLUMN "object_id" SET NOT NULL;
COMMIT;
