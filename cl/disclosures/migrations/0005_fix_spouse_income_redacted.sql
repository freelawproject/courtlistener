-- This change is small and simple.  The text T/F automatically converts to the
-- correct boolean value.

BEGIN;
--
-- Alter field redacted on spouseincome
--
ALTER TABLE "disclosures_spouseincome" ALTER COLUMN "redacted" TYPE boolean USING "redacted"::boolean;
COMMIT;
