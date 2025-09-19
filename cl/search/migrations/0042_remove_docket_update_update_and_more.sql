BEGIN;
--
-- Add field docket_number_raw to docket
--
ALTER TABLE "search_docket" ADD COLUMN "docket_number_raw" varchar NULL;
--
-- Add field docket_number_raw to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "docket_number_raw" varchar NULL;
COMMIT;
