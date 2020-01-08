BEGIN;
--
-- Alter field sha1 on opinion
--
ALTER TABLE "search_opinion" ALTER COLUMN "sha1" SET DEFAULT '';
ALTER TABLE "search_opinion" ALTER COLUMN "sha1" DROP DEFAULT;
COMMIT;
