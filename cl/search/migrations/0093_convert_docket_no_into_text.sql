BEGIN;
--
-- Alter field docket_number on docket
--
ALTER TABLE "search_docket" ALTER COLUMN "docket_number" TYPE text USING "docket_number"::text;
COMMIT;
