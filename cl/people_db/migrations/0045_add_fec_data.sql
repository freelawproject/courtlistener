BEGIN;
--
-- Create model Committee
--
CREATE TABLE "people_db_committee" ("id" serial NOT NULL PRIMARY KEY, "committee_id" varchar(9) NOT NULL, "committee_name" varchar(200) NOT NULL, "committee_party" varchar(3) NOT NULL, "candidate_id" varchar(9) NOT NULL, "connected_org_name" varchar(200) NOT NULL, "committee_type" varchar(1) NOT NULL, "committee_designation" varchar(1) NOT NULL, "org_type" varchar(1) NOT NULL);
--
-- Create model Contribution
--
CREATE TABLE "people_db_contribution" ("id" serial NOT NULL PRIMARY KEY, "valid" boolean NULL, "dt_transaction" date NOT NULL, "transaction_amt" integer NOT NULL, "sub_id" varchar(19) NOT NULL, "transaction_id" varchar(32) NOT NULL, "image_num" varchar(18) NOT NULL, "transaction_pgi" varchar(5) NOT NULL, "year" integer NOT NULL, "transaction_type" varchar(3) NOT NULL, "amend_indicator" varchar(1) NOT NULL, "report_type" varchar(3) NOT NULL, "memo_cd" varchar(1) NOT NULL, "memo_text" varchar(100) NOT NULL, "file_num" varchar(22) NOT NULL);
--
-- Create model Individual
--
CREATE TABLE "people_db_individual" ("id" serial NOT NULL PRIMARY KEY, "name" varchar(200) NOT NULL, "city" varchar(30) NOT NULL, "state" varchar(2) NOT NULL, "zip_code" varchar(9) NOT NULL, "employer" varchar(38) NOT NULL, "occupation" varchar(38) NOT NULL);
CREATE TABLE "people_db_individual_committees" ("id" serial NOT NULL PRIMARY KEY, "individual_id" integer NOT NULL, "committee_id" integer NOT NULL);
--
-- Add field contributor to contribution
--
ALTER TABLE "people_db_contribution" ADD COLUMN "contributor_id" integer NOT NULL;
CREATE INDEX "people_db_committee_committee_id_83d5c845" ON "people_db_committee" ("committee_id");
CREATE INDEX "people_db_committee_committee_id_83d5c845_like" ON "people_db_committee" ("committee_id" varchar_pattern_ops);
CREATE INDEX "people_db_contribution_sub_id_c17aab73" ON "people_db_contribution" ("sub_id");
CREATE INDEX "people_db_contribution_sub_id_c17aab73_like" ON "people_db_contribution" ("sub_id" varchar_pattern_ops);
CREATE INDEX "people_db_contribution_image_num_a2b3288c" ON "people_db_contribution" ("image_num");
CREATE INDEX "people_db_contribution_image_num_a2b3288c_like" ON "people_db_contribution" ("image_num" varchar_pattern_ops);
CREATE INDEX "people_db_individual_name_de90450c" ON "people_db_individual" ("name");
CREATE INDEX "people_db_individual_name_de90450c_like" ON "people_db_individual" ("name" varchar_pattern_ops);
ALTER TABLE "people_db_individual_committees" ADD CONSTRAINT "people_db_individual_individual_id_aa6bb3ee_fk_people_db" FOREIGN KEY ("individual_id") REFERENCES "people_db_individual" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "people_db_individual_committees" ADD CONSTRAINT "people_db_individual_committee_id_f65f9e0e_fk_people_db" FOREIGN KEY ("committee_id") REFERENCES "people_db_committee" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "people_db_individual_committees" ADD CONSTRAINT "people_db_individual_com_individual_id_committee__5adfeff4_uniq" UNIQUE ("individual_id", "committee_id");
CREATE INDEX "people_db_individual_committees_individual_id_aa6bb3ee" ON "people_db_individual_committees" ("individual_id");
CREATE INDEX "people_db_individual_committees_committee_id_f65f9e0e" ON "people_db_individual_committees" ("committee_id");
CREATE INDEX "people_db_contribution_contributor_id_b89c98e5" ON "people_db_contribution" ("contributor_id");
ALTER TABLE "people_db_contribution" ADD CONSTRAINT "people_db_contributi_contributor_id_b89c98e5_fk_people_db" FOREIGN KEY ("contributor_id") REFERENCES "people_db_individual" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
