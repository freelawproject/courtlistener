BEGIN;
--
-- Create model CaseInformation
--
CREATE TABLE "lasc_caseinformation" ("id" serial NOT NULL PRIMARY KEY, "case_id" text NULL, "case_number" varchar(30) NOT NULL, "disposition_type" text NULL, "disposition_type_code" text NULL, "filing_date" date NULL, "filing_date_string" text NULL, "disposition_date" date NULL, "disposition_date_string" text NULL, "district" varchar(10) NOT NULL, "case_type_description" text NOT NULL, "case_type_code" varchar(5) NOT NULL, "case_title" text NOT NULL, "division_code" varchar(10) NOT NULL, "judge_code" varchar(10) NULL, "judicial_officer" text NULL, "courthouse" text NOT NULL, "case_type" integer NULL, "status" text NULL, "status_date" text NULL, "status_code" text NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL);
--
-- Create model CrossReferences
--
CREATE TABLE "lasc_crossreferences" ("id" serial NOT NULL PRIMARY KEY, "cross_reference_date_string" text NULL, "cross_reference_date" timestamp with time zone NULL, "cross_reference_case_number" text NULL, "cross_reference_type_description" text NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL);
--
-- Create model Docket
--
CREATE TABLE "lasc_docket" ("id" serial NOT NULL PRIMARY KEY, "case_id" varchar(30) NOT NULL, "full_data_model" boolean NOT NULL, "date_checked" timestamp with time zone NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "case_hash" varchar(128) NOT NULL);
--
-- Create model DocumentImages
--
CREATE TABLE "lasc_documentimages" ("id" serial NOT NULL PRIMARY KEY, "page_count" integer NOT NULL, "document_type" text NULL, "document_url" text NOT NULL, "create_date" text NOT NULL, "create_date_string" text NOT NULL, "doc_filing_date" date NOT NULL, "doc_filing_date_string" text NOT NULL, "image_type_id" text NOT NULL, "app_id" text NOT NULL, "doc_id" text NOT NULL, "document_type_id" text NOT NULL, "odyssey_id" text NULL, "is_downloadable" boolean NOT NULL, "is_viewable" boolean NOT NULL, "is_emailable" boolean NOT NULL, "is_purchaseable" text NOT NULL, "is_purchased" boolean NOT NULL, "downloaded" boolean NOT NULL, "security_level" text NULL, "description" text NULL, "volume" text NULL, "doc_part" text NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "Docket_id" integer NULL);
--
-- Create model DocumentsFiled
--
CREATE TABLE "lasc_documentsfiled" ("id" serial NOT NULL PRIMARY KEY, "case_number" varchar(20) NOT NULL, "date_filed" timestamp with time zone NOT NULL, "date_filed_string" varchar(25) NOT NULL, "memo" text NULL, "party" text NULL, "document" text NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "Docket_id" integer NULL);
--
-- Create model Parties
--
CREATE TABLE "lasc_parties" ("id" serial NOT NULL PRIMARY KEY, "case_number" text NOT NULL, "district" text NOT NULL, "division_code" text NOT NULL, "attorney_name" text NOT NULL, "attorney_firm" text NOT NULL, "entity_number" text NOT NULL, "party_flag" text NOT NULL, "party_type_code" text NOT NULL, "party_description" text NOT NULL, "name" text NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "Docket_id" integer NULL);
--
-- Create model Proceedings
--
CREATE TABLE "lasc_proceedings" ("id" serial NOT NULL PRIMARY KEY, "am_pm" text NOT NULL, "memo" text NOT NULL, "address" text NOT NULL, "proceeding_date" text NOT NULL, "proceeding_date_string" text NOT NULL, "proceeding_room" text NOT NULL, "proceeding_time" text NOT NULL, "result" text NOT NULL, "judge" text NOT NULL, "courthouse_name" text NOT NULL, "division_code" text NOT NULL, "event" text NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "past_or_future" smallint NULL, "Docket_id" integer NULL);
--
-- Create model RegisterOfActions
--
CREATE TABLE "lasc_registerofactions" ("id" serial NOT NULL PRIMARY KEY, "description" text NOT NULL, "additional_information" text NOT NULL, "register_of_action_date_string" text NOT NULL, "register_of_action_date" timestamp with time zone NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "Docket_id" integer NULL);
--
-- Create model TentativeRulings
--
CREATE TABLE "lasc_tentativerulings" ("id" serial NOT NULL PRIMARY KEY, "case_number" text NOT NULL, "location_id" text NOT NULL, "department" text NOT NULL, "ruling" text NOT NULL, "creation_date" timestamp with time zone NOT NULL, "creation_date_string" text NOT NULL, "hearing_date" timestamp with time zone NOT NULL, "hearing_date_string" text NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "Docket_id" integer NULL);
--
-- Add field Docket to crossreferences
--
ALTER TABLE "lasc_crossreferences" ADD COLUMN "Docket_id" integer NULL;
--
-- Add field Docket to caseinformation
--
ALTER TABLE "lasc_caseinformation" ADD COLUMN "Docket_id" integer NOT NULL;
CREATE INDEX "lasc_caseinformation_date_created_2d76fe5a" ON "lasc_caseinformation" ("date_created");
CREATE INDEX "lasc_caseinformation_date_modified_a64f37e3" ON "lasc_caseinformation" ("date_modified");
CREATE INDEX "lasc_crossreferences_date_created_f2f0ec0a" ON "lasc_crossreferences" ("date_created");
CREATE INDEX "lasc_crossreferences_date_modified_0fd179cf" ON "lasc_crossreferences" ("date_modified");
CREATE INDEX "lasc_docket_date_created_0046364b" ON "lasc_docket" ("date_created");
CREATE INDEX "lasc_docket_date_modified_1185b783" ON "lasc_docket" ("date_modified");
ALTER TABLE "lasc_documentimages" ADD CONSTRAINT "lasc_documentimages_Docket_id_de54e4ec_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_documentimages_date_created_399d2633" ON "lasc_documentimages" ("date_created");
CREATE INDEX "lasc_documentimages_date_modified_70be44b4" ON "lasc_documentimages" ("date_modified");
CREATE INDEX "lasc_documentimages_Docket_id_de54e4ec" ON "lasc_documentimages" ("Docket_id");
ALTER TABLE "lasc_documentsfiled" ADD CONSTRAINT "lasc_documentsfiled_Docket_id_68af105a_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_documentsfiled_date_created_1080cbb9" ON "lasc_documentsfiled" ("date_created");
CREATE INDEX "lasc_documentsfiled_date_modified_7da0c4e2" ON "lasc_documentsfiled" ("date_modified");
CREATE INDEX "lasc_documentsfiled_Docket_id_68af105a" ON "lasc_documentsfiled" ("Docket_id");
ALTER TABLE "lasc_parties" ADD CONSTRAINT "lasc_parties_Docket_id_9088c064_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_parties_date_created_d354644c" ON "lasc_parties" ("date_created");
CREATE INDEX "lasc_parties_date_modified_7e06064c" ON "lasc_parties" ("date_modified");
CREATE INDEX "lasc_parties_Docket_id_9088c064" ON "lasc_parties" ("Docket_id");
ALTER TABLE "lasc_proceedings" ADD CONSTRAINT "lasc_proceedings_Docket_id_73ca6ce0_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_proceedings_date_created_2e30d687" ON "lasc_proceedings" ("date_created");
CREATE INDEX "lasc_proceedings_date_modified_170f588c" ON "lasc_proceedings" ("date_modified");
CREATE INDEX "lasc_proceedings_Docket_id_73ca6ce0" ON "lasc_proceedings" ("Docket_id");
ALTER TABLE "lasc_registerofactions" ADD CONSTRAINT "lasc_registerofactions_Docket_id_49fe1f4c_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_registerofactions_date_created_56008b3b" ON "lasc_registerofactions" ("date_created");
CREATE INDEX "lasc_registerofactions_date_modified_dad7b34f" ON "lasc_registerofactions" ("date_modified");
CREATE INDEX "lasc_registerofactions_Docket_id_49fe1f4c" ON "lasc_registerofactions" ("Docket_id");
ALTER TABLE "lasc_tentativerulings" ADD CONSTRAINT "lasc_tentativerulings_Docket_id_6e661620_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_tentativerulings_date_created_5fc45665" ON "lasc_tentativerulings" ("date_created");
CREATE INDEX "lasc_tentativerulings_date_modified_1eec4328" ON "lasc_tentativerulings" ("date_modified");
CREATE INDEX "lasc_tentativerulings_Docket_id_6e661620" ON "lasc_tentativerulings" ("Docket_id");
CREATE INDEX "lasc_crossreferences_Docket_id_9b94e3d8" ON "lasc_crossreferences" ("Docket_id");
ALTER TABLE "lasc_crossreferences" ADD CONSTRAINT "lasc_crossreferences_Docket_id_9b94e3d8_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_caseinformation_Docket_id_1ab5774e" ON "lasc_caseinformation" ("Docket_id");
ALTER TABLE "lasc_caseinformation" ADD CONSTRAINT "lasc_caseinformation_Docket_id_1ab5774e_fk_lasc_docket_id" FOREIGN KEY ("Docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
