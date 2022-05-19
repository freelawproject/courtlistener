BEGIN;
--
-- Remove field cl_id from person
--
ALTER TABLE "people_db_person" DROP COLUMN "cl_id" CASCADE;
COMMIT;
