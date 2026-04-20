BEGIN;
--
-- Add field source to prayer
--
ALTER TABLE "favorites_prayer" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "favorites_prayer" ALTER COLUMN "source" DROP DEFAULT;

COMMIT;
