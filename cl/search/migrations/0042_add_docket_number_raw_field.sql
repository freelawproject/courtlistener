BEGIN;
--
-- Add field docket_number_raw to docket
--
ALTER TABLE "search_docket" ADD COLUMN "docket_number_raw" varchar DEFAULT '' NOT NULL;
ALTER TABLE "search_docket" ALTER COLUMN "docket_number_raw" DROP DEFAULT;
--
-- Add field docket_number_raw to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "docket_number_raw" varchar DEFAULT '' NOT NULL;
ALTER TABLE "search_docketevent" ALTER COLUMN "docket_number_raw" DROP DEFAULT;

COMMIT;
