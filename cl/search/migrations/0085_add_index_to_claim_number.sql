BEGIN;
--
-- Change Meta options on bankruptcyinformation
--
--
-- Change Meta options on claimhistory
--
--
-- Alter field docket on bankruptcyinformation
--
SET CONSTRAINTS "search_bankruptcyinf_docket_id_91fa3275_fk_search_do" IMMEDIATE;
ALTER TABLE "search_bankruptcyinformation"
    DROP CONSTRAINT "search_bankruptcyinf_docket_id_91fa3275_fk_search_do";
ALTER TABLE "search_bankruptcyinformation"
    ADD CONSTRAINT "search_bankruptcyinf_docket_id_91fa3275_fk_search_do" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Alter field claim_number on claim
--
CREATE INDEX "search_claim_claim_number_263236b3" ON "search_claim" ("claim_number");
CREATE INDEX "search_claim_claim_number_263236b3_like" ON "search_claim" ("claim_number" varchar_pattern_ops);
--
-- Alter field thumbnail on claimhistory
--
--
-- Alter field thumbnail on recapdocument
--
COMMIT;
