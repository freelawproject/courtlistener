BEGIN;
--
-- Add field pro_se to partytype
--
ALTER TABLE "people_db_partytype" ADD COLUMN "pro_se" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "people_db_partytype" ALTER COLUMN "pro_se" DROP DEFAULT;
COMMIT;
