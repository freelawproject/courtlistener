BEGIN;
--
-- Rename unnamed index for ('docket_number', 'district', 'division_code') on docket to lasc_docket_docket__4b4f04_idx
--
ALTER INDEX "lasc_docket_docket_number_district_division_code_07584433_idx" RENAME TO "lasc_docket_docket__4b4f04_idx";
COMMIT;
