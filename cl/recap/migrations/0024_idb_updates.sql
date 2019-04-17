BEGIN;
ALTER TABLE "recap_fjcintegrateddatabase" DROP COLUMN "case_name" CASCADE;
ALTER TABLE "recap_fjcintegrateddatabase" DROP COLUMN "pacer_case_id" CASCADE;

COMMIT;
