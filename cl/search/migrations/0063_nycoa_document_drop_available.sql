BEGIN;
--
-- Remove field available from nycoadocument
--
ALTER TABLE "search_nycoadocument" DROP COLUMN "available";
--
-- Remove field available from nycoadocumentevent
--
ALTER TABLE "search_nycoadocumentevent" DROP COLUMN "available";
COMMIT;
