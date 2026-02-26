BEGIN;
--
-- Add field docket_number_source to docket
--
ALTER TABLE "search_docket" ADD COLUMN "docket_number_source" smallint DEFAULT 0 NOT NULL CHECK ("docket_number_source" >= 0);
ALTER TABLE "search_docket" ALTER COLUMN "docket_number_source" DROP DEFAULT;
--
-- Add field docket_number_source to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "docket_number_source" smallint DEFAULT 0 NOT NULL CHECK ("docket_number_source" >= 0);
ALTER TABLE "search_docketevent" ALTER COLUMN "docket_number_source" DROP DEFAULT;
COMMIT;