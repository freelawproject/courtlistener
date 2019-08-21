BEGIN;
--
-- Remove field case_number from documentsfiled
--
ALTER TABLE "lasc_documentsfiled" DROP COLUMN "case_number" CASCADE;
--
-- Remove field case_number from parties
--
ALTER TABLE "lasc_parties" DROP COLUMN "case_number" CASCADE;
--
-- Remove field district from parties
--
ALTER TABLE "lasc_parties" DROP COLUMN "district" CASCADE;
--
-- Remove field division_code from parties
--
ALTER TABLE "lasc_parties" DROP COLUMN "division_code" CASCADE;
--
-- Alter field disposition_date on caseinformation
--
--
-- Alter field disposition_date_string on caseinformation
--
--
-- Alter field filing_date on caseinformation
--
--
-- Alter field filing_date_string on caseinformation
--
--
-- Alter field case_hash on docket
--
--
-- Alter field document_type on documentimages
--
--
-- Alter field party on documentsfiled
--
--
-- Alter field past_or_future on proceedings
--
--
-- Alter field register_of_action_date_string on registerofactions
--
--
-- Alter field ruling on tentativerulings
--
COMMIT;
