BEGIN;
--
-- Create model BankruptcyInformation
--
CREATE TABLE "search_bankruptcyinformation" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_converted" timestamp with time zone NULL, "date_last_to_file_claims" timestamp with time zone NULL, "date_last_to_file_govt" timestamp with time zone NULL, "date_debtor_dismissed" timestamp with time zone NULL, "chapter" varchar(10) NOT NULL, "trustee_str" text NOT NULL, "docket_id" integer NOT NULL UNIQUE);
--
-- Create model Claim
--
CREATE TABLE "search_claim" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_claim_modified" timestamp with time zone NULL, "date_original_entered" timestamp with time zone NULL, "date_original_filed" timestamp with time zone NULL, "date_last_amendment_entered" timestamp with time zone NULL, "date_last_amendment_filed" timestamp with time zone NULL, "claim_number" varchar(10) NOT NULL, "creditor_details" text NOT NULL, "creditor_id" varchar(50) NOT NULL, "status" varchar(1000) NOT NULL, "entered_by" varchar(1000) NOT NULL, "filed_by" varchar(1000) NOT NULL, "amount_claimed" varchar(100) NOT NULL, "unsecured_claimed" varchar(100) NOT NULL, "secured_claimed" varchar(100) NOT NULL, "priority_claimed" varchar(100) NOT NULL, "description" text NOT NULL, "remarks" text NOT NULL, "docket_id" integer NOT NULL);
CREATE TABLE "search_claim_tags" ("id" serial NOT NULL PRIMARY KEY, "claim_id" integer NOT NULL, "tag_id" integer NOT NULL);
--
-- Create model ClaimHistory
--
CREATE TABLE "search_claimhistory" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_upload" timestamp with time zone NULL, "document_number" varchar(32) NOT NULL, "attachment_number" smallint NULL, "pacer_doc_id" varchar(32) NOT NULL, "is_available" boolean NULL, "sha1" varchar(40) NOT NULL, "page_count" integer NULL, "file_size" integer NULL, "filepath_local" varchar(1000) NOT NULL, "filepath_ia" varchar(1000) NOT NULL, "ia_upload_failure_count" smallint NULL, "thumbnail" varchar(100) NULL, "thumbnail_status" smallint NOT NULL, "plain_text" text NOT NULL, "ocr_status" smallint NULL, "is_free_on_pacer" boolean NULL, "is_sealed" boolean NULL, "date_filed" date NULL, "claim_document_type" integer NOT NULL, "description" text NOT NULL, "claim_doc_id" varchar(32) NOT NULL, "pacer_dm_id" integer NULL, "pacer_case_id" varchar(100) NOT NULL, "claim_id" integer NOT NULL);
--
-- Do indexes and constraints
--
ALTER TABLE "search_bankruptcyinformation" ADD CONSTRAINT "search_bankruptcyinf_docket_id_91fa3275_fk_search_do" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_bankruptcyinformation_date_created_60f180b0" ON "search_bankruptcyinformation" ("date_created");
CREATE INDEX "search_bankruptcyinformation_date_modified_c1b76dd9" ON "search_bankruptcyinformation" ("date_modified");
ALTER TABLE "search_claim" ADD CONSTRAINT "search_claim_docket_id_b37171a9_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_claim_date_created_8c2e998c" ON "search_claim" ("date_created");
CREATE INDEX "search_claim_date_modified_f38130a2" ON "search_claim" ("date_modified");
CREATE INDEX "search_claim_docket_id_b37171a9" ON "search_claim" ("docket_id");
ALTER TABLE "search_claim_tags" ADD CONSTRAINT "search_claim_tags_claim_id_2cf554b5_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_claim_tags" ADD CONSTRAINT "search_claim_tags_tag_id_73b6bd4d_fk_search_tag_id" FOREIGN KEY ("tag_id") REFERENCES "search_tag" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_claim_tags" ADD CONSTRAINT "search_claim_tags_claim_id_tag_id_2f236693_uniq" UNIQUE ("claim_id", "tag_id");
CREATE INDEX "search_claim_tags_claim_id_2cf554b5" ON "search_claim_tags" ("claim_id");
CREATE INDEX "search_claim_tags_tag_id_73b6bd4d" ON "search_claim_tags" ("tag_id");
ALTER TABLE "search_claimhistory" ADD CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_claimhistory_date_created_586d545e" ON "search_claimhistory" ("date_created");
CREATE INDEX "search_claimhistory_date_modified_5f6ec339" ON "search_claimhistory" ("date_modified");
CREATE INDEX "search_claimhistory_document_number_6316c155" ON "search_claimhistory" ("document_number");
CREATE INDEX "search_claimhistory_document_number_6316c155_like" ON "search_claimhistory" ("document_number" varchar_pattern_ops);
CREATE INDEX "search_claimhistory_filepath_local_c52db4fc" ON "search_claimhistory" ("filepath_local");
CREATE INDEX "search_claimhistory_filepath_local_c52db4fc_like" ON "search_claimhistory" ("filepath_local" varchar_pattern_ops);
CREATE INDEX "search_claimhistory_is_free_on_pacer_81332a2c" ON "search_claimhistory" ("is_free_on_pacer");
CREATE INDEX "search_claimhistory_is_sealed_80556d76" ON "search_claimhistory" ("is_sealed");
CREATE INDEX "search_claimhistory_claim_id_e130e572" ON "search_claimhistory" ("claim_id");
COMMIT;
