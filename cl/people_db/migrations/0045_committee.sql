BEGIN;
--
-- Create model Committee
--
CREATE TABLE "people_db_committee" ("id" serial NOT NULL PRIMARY KEY, "committee_uniq_id" varchar(9) NOT NULL, "committee_name" varchar(200) NOT NULL, "committee_party" varchar(3) NOT NULL, "candidate_id" varchar(9) NOT NULL, "connected_org_name" varchar(200) NOT NULL, "committee_type" varchar(1) NOT NULL, "committee_designation" varchar(1) NOT NULL, "org_type" varchar(1) NOT NULL);
CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba" ON "people_db_committee" ("committee_uniq_id");
CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba_like" ON "people_db_committee" ("committee_uniq_id" varchar_pattern_ops);
COMMIT;
