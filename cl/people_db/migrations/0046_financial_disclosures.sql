CREATE TABLE "people_db_agreements" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "parties_and_terms" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_debt" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "creditor_name" text NOT NULL, "description" text NOT NULL, "value_code" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_gift" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "description" text NOT NULL, "value_code" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_investment" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "description" text NOT NULL, "redacted" boolean NOT NULL, "income_during_reporting_period_code" text NOT NULL, "income_during_reporting_period_type" text NOT NULL, "gross_value_code" text NOT NULL, "gross_value_method" text NOT NULL, "transaction_during_reporting_period" text NOT NULL, "transaction_date_raw" text NOT NULL, "transaction_value_code" text NOT NULL, "transaction_gain_code" text NOT NULL, "transaction_partner" text NOT NULL, "has_inferred_values" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_noninvestmentincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "source_type" text NOT NULL, "income_amount" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_positions" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "position" text NOT NULL, "organization_name" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_reimbursement" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "dates" text NOT NULL, "location" text NOT NULL, "purpose" text NOT NULL, "items_paid_or_provided" text NOT NULL, "redacted" boolean NOT NULL); (params None)"
CREATE TABLE "people_db_spouseincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source_type" text NOT NULL, "date" text NOT NULL, "redacted" text NOT NULL); (params None)"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "addendum_content_raw" text DEFAULT %s NOT NULL; (params [''])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "addendum_content_raw" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "addendum_redacted" boolean DEFAULT %s NOT NULL; (params [False])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "addendum_redacted" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "date_created" timestamp with time zone DEFAULT %s NOT NULL; (params [datetime.datetime(2020, 12, 17, 18, 56, 3, 585086, tzinfo=<UTC>)])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "date_created" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "date_modified" timestamp with time zone DEFAULT %s NOT NULL; (params [datetime.datetime(2020, 12, 17, 18, 56, 3, 615865, tzinfo=<UTC>)])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "date_modified" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "has_been_extracted" boolean DEFAULT %s NOT NULL; (params [False])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "has_been_extracted" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "is_amended" boolean DEFAULT %s NOT NULL; (params [False])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "is_amended" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "pdf_hash" varchar(40) DEFAULT %s NOT NULL; (params [''])"
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "pdf_hash" DROP DEFAULT; (params ())"
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "report_type" text NULL; (params [])"
ALTER TABLE "people_db_spouseincome" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_reimbursement" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_positions" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_noninvestmentincome" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_investment" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_gift" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_debt" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
ALTER TABLE "people_db_agreements" ADD COLUMN "financial_disclosure_id" integer NOT NULL; (params [])"
CREATE INDEX "people_db_agreements_date_created_f0072fe9" ON "people_db_agreements" ("date_created"); (params ())"
CREATE INDEX "people_db_agreements_date_modified_1472fe71" ON "people_db_agreements" ("date_modified"); (params ())"
CREATE INDEX "people_db_debt_date_created_e3d73a53" ON "people_db_debt" ("date_created"); (params ())"
CREATE INDEX "people_db_debt_date_modified_4c08f759" ON "people_db_debt" ("date_modified"); (params ())"
CREATE INDEX "people_db_gift_date_created_9a8683a9" ON "people_db_gift" ("date_created"); (params ())"
CREATE INDEX "people_db_gift_date_modified_1e90ca76" ON "people_db_gift" ("date_modified"); (params ())"
CREATE INDEX "people_db_investment_date_created_9533dc25" ON "people_db_investment" ("date_created"); (params ())"
CREATE INDEX "people_db_investment_date_modified_493bf724" ON "people_db_investment" ("date_modified"); (params ())"
CREATE INDEX "people_db_noninvestmentincome_date_created_3d28ad0b" ON "people_db_noninvestmentincome" ("date_created"); (params ())"
CREATE INDEX "people_db_noninvestmentincome_date_modified_5db3509f" ON "people_db_noninvestmentincome" ("date_modified"); (params ())"
CREATE INDEX "people_db_positions_date_created_7885b48c" ON "people_db_positions" ("date_created"); (params ())"
CREATE INDEX "people_db_positions_date_modified_090bf76e" ON "people_db_positions" ("date_modified"); (params ())"
CREATE INDEX "people_db_reimbursement_date_created_896230ae" ON "people_db_reimbursement" ("date_created"); (params ())"
CREATE INDEX "people_db_reimbursement_date_modified_2a2ed1e7" ON "people_db_reimbursement" ("date_modified"); (params ())"
CREATE INDEX "people_db_spouseincome_date_created_fb39ce14" ON "people_db_spouseincome" ("date_created"); (params ())"
CREATE INDEX "people_db_spouseincome_date_modified_e3349b14" ON "people_db_spouseincome" ("date_modified"); (params ())"
CREATE INDEX "people_db_financialdisclosure_date_created_9efd5106" ON "people_db_financialdisclosure" ("date_created"); (params ())"
CREATE INDEX "people_db_financialdisclosure_date_modified_4d6cbad4" ON "people_db_financialdisclosure" ("date_modified"); (params ())"
CREATE INDEX "people_db_financialdisclosure_pdf_hash_7f3b4186" ON "people_db_financialdisclosure" ("pdf_hash"); (params ())"
CREATE INDEX "people_db_financialdisclosure_pdf_hash_7f3b4186_like" ON "people_db_financialdisclosure" ("pdf_hash" varchar_pattern_ops); (params ())"
CREATE INDEX "people_db_spouseincome_financial_disclosure_id_0cf77bfb" ON "people_db_spouseincome" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_spouseincome" ADD CONSTRAINT "people_db_spouseinco_financial_disclosure_0cf77bfb_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_reimbursement_financial_disclosure_id_f6f67662" ON "people_db_reimbursement" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_reimbursement" ADD CONSTRAINT "people_db_reimbursem_financial_disclosure_f6f67662_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_positions_financial_disclosure_id_01b67359" ON "people_db_positions" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_positions" ADD CONSTRAINT "people_db_positions_financial_disclosure_01b67359_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_noninvestmentincome_financial_disclosure_id_1cd823e7" ON "people_db_noninvestmentincome" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_noninvestmentincome" ADD CONSTRAINT "people_db_noninvestm_financial_disclosure_1cd823e7_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_investment_financial_disclosure_id_00e8fdbe" ON "people_db_investment" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_investment" ADD CONSTRAINT "people_db_investment_financial_disclosure_00e8fdbe_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_gift_financial_disclosure_id_c153e599" ON "people_db_gift" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_gift" ADD CONSTRAINT "people_db_gift_financial_disclosure_c153e599_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_debt_financial_disclosure_id_de8afb7d" ON "people_db_debt" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_debt" ADD CONSTRAINT "people_db_debt_financial_disclosure_de8afb7d_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
CREATE INDEX "people_db_agreements_financial_disclosure_id_6a616493" ON "people_db_agreements" ("financial_disclosure_id"); (params ())"
ALTER TABLE "people_db_agreements" ADD CONSTRAINT "people_db_agreements_financial_disclosure_6a616493_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED; (params ())"
BEGIN;
--
-- Create model Agreements
--
CREATE TABLE "people_db_agreements" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "parties_and_terms" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Debt
--
CREATE TABLE "people_db_debt" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "creditor_name" text NOT NULL, "description" text NOT NULL, "value_code" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Gift
--
CREATE TABLE "people_db_gift" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "description" text NOT NULL, "value_code" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Investment
--
CREATE TABLE "people_db_investment" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "description" text NOT NULL, "redacted" boolean NOT NULL, "income_during_reporting_period_code" text NOT NULL, "income_during_reporting_period_type" text NOT NULL, "gross_value_code" text NOT NULL, "gross_value_method" text NOT NULL, "transaction_during_reporting_period" text NOT NULL, "transaction_date_raw" text NOT NULL, "transaction_value_code" text NOT NULL, "transaction_gain_code" text NOT NULL, "transaction_partner" text NOT NULL, "has_inferred_values" boolean NOT NULL);
--
-- Create model NonInvestmentIncome
--
CREATE TABLE "people_db_noninvestmentincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date" text NOT NULL, "source_type" text NOT NULL, "income_amount" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Positions
--
CREATE TABLE "people_db_positions" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "position" text NOT NULL, "organization_name" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model Reimbursement
--
CREATE TABLE "people_db_reimbursement" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" text NOT NULL, "dates" text NOT NULL, "location" text NOT NULL, "purpose" text NOT NULL, "items_paid_or_provided" text NOT NULL, "redacted" boolean NOT NULL);
--
-- Create model SpouseIncome
--
CREATE TABLE "people_db_spouseincome" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source_type" text NOT NULL, "date" text NOT NULL, "redacted" text NOT NULL);
--
-- Add field addendum_content_raw to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "addendum_content_raw" text DEFAULT '' NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "addendum_content_raw" DROP DEFAULT;
--
-- Add field addendum_redacted to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "addendum_redacted" boolean DEFAULT false NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "addendum_redacted" DROP DEFAULT;
--
-- Add field date_created to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "date_created" timestamp with time zone DEFAULT '2020-12-17T18:56:03.585086+00:00'::timestamptz NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Add field date_modified to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "date_modified" timestamp with time zone DEFAULT '2020-12-17T18:56:03.615865+00:00'::timestamptz NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Add field has_been_extracted to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "has_been_extracted" boolean DEFAULT false NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "has_been_extracted" DROP DEFAULT;
--
-- Add field is_amended to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "is_amended" boolean DEFAULT false NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "is_amended" DROP DEFAULT;
--
-- Add field pdf_hash to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "pdf_hash" varchar(40) DEFAULT '' NOT NULL;
ALTER TABLE "people_db_financialdisclosure" ALTER COLUMN "pdf_hash" DROP DEFAULT;
--
-- Add field report_type to financialdisclosure
--
ALTER TABLE "people_db_financialdisclosure" ADD COLUMN "report_type" text NULL;
--
-- Alter field filepath on financialdisclosure
--
--
-- Add field financial_disclosure to spouseincome
--
ALTER TABLE "people_db_spouseincome" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to reimbursement
--
ALTER TABLE "people_db_reimbursement" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to positions
--
ALTER TABLE "people_db_positions" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to noninvestmentincome
--
ALTER TABLE "people_db_noninvestmentincome" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to investment
--
ALTER TABLE "people_db_investment" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to gift
--
ALTER TABLE "people_db_gift" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to debt
--
ALTER TABLE "people_db_debt" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field financial_disclosure to agreements
--
ALTER TABLE "people_db_agreements" ADD COLUMN "financial_disclosure_id" integer NOT NULL;
CREATE INDEX "people_db_agreements_date_created_f0072fe9" ON "people_db_agreements" ("date_created");
CREATE INDEX "people_db_agreements_date_modified_1472fe71" ON "people_db_agreements" ("date_modified");
CREATE INDEX "people_db_debt_date_created_e3d73a53" ON "people_db_debt" ("date_created");
CREATE INDEX "people_db_debt_date_modified_4c08f759" ON "people_db_debt" ("date_modified");
CREATE INDEX "people_db_gift_date_created_9a8683a9" ON "people_db_gift" ("date_created");
CREATE INDEX "people_db_gift_date_modified_1e90ca76" ON "people_db_gift" ("date_modified");
CREATE INDEX "people_db_investment_date_created_9533dc25" ON "people_db_investment" ("date_created");
CREATE INDEX "people_db_investment_date_modified_493bf724" ON "people_db_investment" ("date_modified");
CREATE INDEX "people_db_noninvestmentincome_date_created_3d28ad0b" ON "people_db_noninvestmentincome" ("date_created");
CREATE INDEX "people_db_noninvestmentincome_date_modified_5db3509f" ON "people_db_noninvestmentincome" ("date_modified");
CREATE INDEX "people_db_positions_date_created_7885b48c" ON "people_db_positions" ("date_created");
CREATE INDEX "people_db_positions_date_modified_090bf76e" ON "people_db_positions" ("date_modified");
CREATE INDEX "people_db_reimbursement_date_created_896230ae" ON "people_db_reimbursement" ("date_created");
CREATE INDEX "people_db_reimbursement_date_modified_2a2ed1e7" ON "people_db_reimbursement" ("date_modified");
CREATE INDEX "people_db_spouseincome_date_created_fb39ce14" ON "people_db_spouseincome" ("date_created");
CREATE INDEX "people_db_spouseincome_date_modified_e3349b14" ON "people_db_spouseincome" ("date_modified");
CREATE INDEX "people_db_financialdisclosure_date_created_9efd5106" ON "people_db_financialdisclosure" ("date_created");
CREATE INDEX "people_db_financialdisclosure_date_modified_4d6cbad4" ON "people_db_financialdisclosure" ("date_modified");
CREATE INDEX "people_db_financialdisclosure_pdf_hash_7f3b4186" ON "people_db_financialdisclosure" ("pdf_hash");
CREATE INDEX "people_db_financialdisclosure_pdf_hash_7f3b4186_like" ON "people_db_financialdisclosure" ("pdf_hash" varchar_pattern_ops);
CREATE INDEX "people_db_spouseincome_financial_disclosure_id_0cf77bfb" ON "people_db_spouseincome" ("financial_disclosure_id");
ALTER TABLE "people_db_spouseincome" ADD CONSTRAINT "people_db_spouseinco_financial_disclosure_0cf77bfb_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_reimbursement_financial_disclosure_id_f6f67662" ON "people_db_reimbursement" ("financial_disclosure_id");
ALTER TABLE "people_db_reimbursement" ADD CONSTRAINT "people_db_reimbursem_financial_disclosure_f6f67662_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_positions_financial_disclosure_id_01b67359" ON "people_db_positions" ("financial_disclosure_id");
ALTER TABLE "people_db_positions" ADD CONSTRAINT "people_db_positions_financial_disclosure_01b67359_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_noninvestmentincome_financial_disclosure_id_1cd823e7" ON "people_db_noninvestmentincome" ("financial_disclosure_id");
ALTER TABLE "people_db_noninvestmentincome" ADD CONSTRAINT "people_db_noninvestm_financial_disclosure_1cd823e7_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_investment_financial_disclosure_id_00e8fdbe" ON "people_db_investment" ("financial_disclosure_id");
ALTER TABLE "people_db_investment" ADD CONSTRAINT "people_db_investment_financial_disclosure_00e8fdbe_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_gift_financial_disclosure_id_c153e599" ON "people_db_gift" ("financial_disclosure_id");
ALTER TABLE "people_db_gift" ADD CONSTRAINT "people_db_gift_financial_disclosure_c153e599_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_debt_financial_disclosure_id_de8afb7d" ON "people_db_debt" ("financial_disclosure_id");
ALTER TABLE "people_db_debt" ADD CONSTRAINT "people_db_debt_financial_disclosure_de8afb7d_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "people_db_agreements_financial_disclosure_id_6a616493" ON "people_db_agreements" ("financial_disclosure_id");
ALTER TABLE "people_db_agreements" ADD CONSTRAINT "people_db_agreements_financial_disclosure_6a616493_fk_people_db" FOREIGN KEY ("financial_disclosure_id") REFERENCES "people_db_financialdisclosure" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
