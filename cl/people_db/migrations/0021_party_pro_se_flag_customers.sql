BEGIN;
--
-- Add field pro_se_flag to party
--
ALTER TABLE "people_db_party" ADD COLUMN "pro_se_flag" boolean DEFAULT false NOT NULL;
ALTER TABLE "people_db_party" ALTER COLUMN "pro_se_flag" DROP DEFAULT;
COMMIT;
