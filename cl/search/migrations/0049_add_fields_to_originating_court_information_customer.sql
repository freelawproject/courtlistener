BEGIN;
--
-- Add field date_rehearing_denied to originatingcourtinformation
--
ALTER TABLE "search_originatingcourtinformation" ADD COLUMN "date_rehearing_denied" date NULL;
--
-- Add field docket_number_raw to originatingcourtinformation
--
ALTER TABLE "search_originatingcourtinformation" ADD COLUMN "docket_number_raw" varchar DEFAULT '' NOT NULL;
ALTER TABLE "search_originatingcourtinformation" ALTER COLUMN "docket_number_raw" DROP DEFAULT;

COMMIT;
