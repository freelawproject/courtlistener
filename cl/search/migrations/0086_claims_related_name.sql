BEGIN;
--
-- Alter field claim on claimhistory
--
SET CONSTRAINTS "search_claimhistory_claim_id_e130e572_fk_search_claim_id" IMMEDIATE; ALTER TABLE "search_claimhistory" DROP CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id";
ALTER TABLE "search_claimhistory" ADD CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
