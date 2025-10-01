BEGIN;
--
-- Alter field volume on unmatchedcitation
--
ALTER TABLE "citations_unmatchedcitation" ALTER COLUMN "volume" TYPE text USING "volume"::text;
COMMIT;
