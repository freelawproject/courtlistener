BEGIN;
--
-- Remove field available from nycoadocument
--
ALTER TABLE "search_nycoadocument" DROP COLUMN "available";
COMMIT;
