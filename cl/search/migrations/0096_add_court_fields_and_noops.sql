BEGIN;
--
-- Add field date_last_pacer_contact to court
--
ALTER TABLE "search_court" ADD COLUMN "date_last_pacer_contact" timestamp with time zone NULL;
--
-- Add field pacer_rss_entry_types to court
--
ALTER TABLE "search_court" ADD COLUMN "pacer_rss_entry_types" text DEFAULT '' NOT NULL;
ALTER TABLE "search_court" ALTER COLUMN "pacer_rss_entry_types" DROP DEFAULT;
--
-- Alter field date_last_filing on docket
--
--
-- Alter field source on opinioncluster
--
--
-- Alter field source on docket
--

COMMIT;
