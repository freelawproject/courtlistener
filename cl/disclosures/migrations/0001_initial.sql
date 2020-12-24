BEGIN;
--
-- Create model Agreement
--
CREATE TABLE "disclosures_agreement" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "parties_and_terms" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Debt
--
CREATE TABLE "disclosures_debt" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "creditor_name" text NOT NULL, "description" text NOT NULL, "value_code" varchar(5) NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model FinancialDisclosure
--
CREATE TABLE "disclosures_financialdisclosure" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "year" smallint NOT NULL, "download_filepath" varchar(100) NOT NULL, "filepath" varchar(100) NOT NULL, "thumbnail" varchar(100) NULL, "thumbnail_status" smallint NOT NULL, "page_count" smallint NOT NULL, "sha1" varchar(40) NOT NULL, "report_type" smallint NOT NULL, "is_amended" boolean NOT NULL, "addendum_content_raw" text NOT NULL, "addendum_redacted" boolean NOT NULL, "has_been_extracted" boolean NOT NULL, "person_id" integer NOT NULL);
--
-- Create model Gift
--
CREATE TABLE "disclosures_gift" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "description" text NOT NULL, "value_code" text NOT NULL, "redacted" boolean NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Create model Investment
--
CREATE TABLE "disclosures_investment" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "page_number" integer NOT NULL, "description" text NOT NULL, "redacted" boolean NOT NULL, "income_during_reporting_period_code" varchar(5) NOT NULL, "income_during_reporting_period_type" text NOT NULL, "gross_value_code" varchar(5) NOT NULL, "gross_value_method" varchar(5) NOT NULL, "transaction_during_reporting_period" text NOT NULL, "transaction_date_raw" varchar(40) NOT NULL, "transaction_date" date NULL, "transaction_value_code" varchar(5) NOT NULL, "transaction_gain_code" varchar(5) NOT NULL, "transaction_partner" text NOT NULL, "has_inferred_values" boolean NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Create model NonInvestmentIncome
--
CREATE TABLE "disclosures_noninvestmentincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "source_type" text NOT NULL, "income_amount" text NOT NULL, "redacted" boolean NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Create model Position
--
CREATE TABLE "disclosures_position" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "position" text NOT NULL, "organization_name" text NOT NULL, "redacted" boolean NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Create model Reimbursement
--
CREATE TABLE "disclosures_reimbursement" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "dates" text NOT NULL, "location" text NOT NULL, "purpose" text NOT NULL, "items_paid_or_provided" text NOT NULL, "redacted" boolean NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Create model SpouseIncome
--
CREATE TABLE "disclosures_spouseincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source_type" text NOT NULL, "date" text NOT NULL, "redacted" text NOT NULL, "financial_disclosure_id" integer NOT NULL);
--
-- Add field financial_disclosure to debt
--
ALTER TABLE "disclosures_debt" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to agreement
--
ALTER TABLE "disclosures_agreement" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
CREATE INDEX "disclosures_agreement_date_created_799a50fa" ON "disclosures_agreement" ("date_created");
CREATE INDEX "disclosures_agreement_date_modified_cf46cbed" ON "disclosures_agreement" ("date_modified");
CREATE INDEX "disclosures_debt_date_created_ed9d5440" ON "disclosures_debt" ("date_created");
CREATE INDEX "disclosures_debt_date_modified_a1482a62" ON "disclosures_debt" ("date_modified");
ALTER TABLE "disclosures_financialdisclosure" ADD CONSTRAINT "disclosures_financia_person_id_83e04c6c_fk_people_db" FOREIGN KEY ("person_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_financialdisclosure_date_created_85a1e80e" ON "disclosures_financialdisclosure" ("date_created");
CREATE INDEX "disclosures_financialdisclosure_date_modified_717ae8fa" ON "disclosures_financialdisclosure" ("date_modified");
CREATE INDEX "disclosures_financialdisclosure_year_ee032263" ON "disclosures_financialdisclosure" ("year");
CREATE INDEX "disclosures_financialdisclosure_filepath_8266edc6" ON "disclosures_financialdisclosure" ("filepath");
CREATE INDEX "disclosures_financialdisclosure_filepath_8266edc6_like" ON "disclosures_financialdisclosure" ("filepath" varchar_pattern_ops);
CREATE INDEX "disclosures_financialdisclosure_sha1_552f12ae" ON "disclosures_financialdisclosure" ("sha1");
CREATE INDEX "disclosures_financialdisclosure_sha1_552f12ae_like" ON "disclosures_financialdisclosure" ("sha1" varchar_pattern_ops);
CREATE INDEX "disclosures_financialdisclosure_person_id_83e04c6c" ON "disclosures_financialdisclosure" ("person_id");
ALTER TABLE "disclosures_gift" ADD CONSTRAINT "disclosures_gift_financial_disclosure_67efabf6_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_gift_date_created_c3e030fc" ON "disclosures_gift" ("date_created");
CREATE INDEX "disclosures_gift_date_modified_ceb7453c" ON "disclosures_gift" ("date_modified");
CREATE INDEX "disclosures_gift_financial_disclosure_id_67efabf6" ON "disclosures_gift" ("financial_disclosure_id");
ALTER TABLE "disclosures_investment" ADD CONSTRAINT "disclosures_investme_financial_disclosure_ad904849_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_investment_date_created_252beaa5" ON "disclosures_investment" ("date_created");
CREATE INDEX "disclosures_investment_date_modified_e2f8f841" ON "disclosures_investment" ("date_modified");
CREATE INDEX "disclosures_investment_financial_disclosure_id_ad904849" ON "disclosures_investment" ("financial_disclosure_id");
ALTER TABLE "disclosures_noninvestmentincome" ADD CONSTRAINT "disclosures_noninves_financial_disclosure_5b351795_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_noninvestmentincome_date_created_d876ac4b" ON "disclosures_noninvestmentincome" ("date_created");
CREATE INDEX "disclosures_noninvestmentincome_date_modified_d3c68c8b" ON "disclosures_noninvestmentincome" ("date_modified");
CREATE INDEX "disclosures_noninvestmenti_financial_disclosure_id_5b351795" ON "disclosures_noninvestmentincome" ("financial_disclosure_id");
ALTER TABLE "disclosures_position" ADD CONSTRAINT "disclosures_position_financial_disclosure_b81030c0_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_position_date_created_e515f4be" ON "disclosures_position" ("date_created");
CREATE INDEX "disclosures_position_date_modified_01fafcba" ON "disclosures_position" ("date_modified");
CREATE INDEX "disclosures_position_financial_disclosure_id_b81030c0" ON "disclosures_position" ("financial_disclosure_id");
ALTER TABLE "disclosures_reimbursement" ADD CONSTRAINT "disclosures_reimburs_financial_disclosure_141ee670_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_reimbursement_date_created_4056c28a" ON "disclosures_reimbursement" ("date_created");
CREATE INDEX "disclosures_reimbursement_date_modified_3ca21f45" ON "disclosures_reimbursement" ("date_modified");
CREATE INDEX "disclosures_reimbursement_financial_disclosure_id_141ee670" ON "disclosures_reimbursement" ("financial_disclosure_id");
ALTER TABLE "disclosures_spouseincome" ADD CONSTRAINT "disclosures_spousein_financial_disclosure_94e0c727_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_spouseincome_date_created_00632eb5" ON "disclosures_spouseincome" ("date_created");
CREATE INDEX "disclosures_spouseincome_date_modified_9bea7dd2" ON "disclosures_spouseincome" ("date_modified");
CREATE INDEX "disclosures_spouseincome_financial_disclosure_id_94e0c727" ON "disclosures_spouseincome" ("financial_disclosure_id");
CREATE INDEX "disclosures_debt_financial_disclosure_id_18a78f4c" ON "disclosures_debt" ("financial_disclosure_id");
ALTER TABLE "disclosures_debt" ADD CONSTRAINT "disclosures_debt_financial_disclosure_18a78f4c_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "disclosures_agreement_financial_disclosure_id_eb38358a" ON "disclosures_agreement" ("financial_disclosure_id");
ALTER TABLE "disclosures_agreement" ADD CONSTRAINT "disclosures_agreemen_financial_disclosure_eb38358a_fk_disclosur" FOREIGN KEY ("financial_disclosure_id") REFERENCES "disclosures_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
