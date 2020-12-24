BEGIN;
--
-- Remove field person from financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" DROP COLUMN "person_id" CASCADE;
--
-- Delete model FinancialDisclosure
--
DROP TABLE "people_db_financialdisclosure" CASCADE;
COMMIT;
