BEGIN;
--
-- Add field date_rehearing_denied to originatingcourtinformation
--
ALTER TABLE "search_originatingcourtinformation" ADD COLUMN "date_rehearing_denied" date NULL;
--
-- Add field date_rehearing_denied to originatingcourtinformationevent
--
ALTER TABLE "search_originatingcourtinformationevent" ADD COLUMN "date_rehearing_denied" date NULL;

COMMIT;
