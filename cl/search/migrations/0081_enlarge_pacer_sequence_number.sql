BEGIN;
ALTER TABLE "search_docketentry" ALTER COLUMN "pacer_sequence_number" TYPE integer;

COMMIT;
