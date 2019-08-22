BEGIN;
--
-- Create model Action
--
CREATE TABLE "lasc_action" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_of_action" timestamp with time zone NOT NULL, "description" text NOT NULL, "additional_information" text NOT NULL);
--
-- Create model CrossReference
--
CREATE TABLE "lasc_crossreference" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_cross_reference" timestamp with time zone NULL, "cross_reference_docket_number" text NOT NULL, "cross_reference_type" text NOT NULL);
--
-- Create model Docket
--
CREATE TABLE "lasc_docket" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_checked" timestamp with time zone NULL, "date_filed" date NULL, "date_disposition" date NULL, "docket_number" varchar(300) NOT NULL, "district" varchar(10) NOT NULL, "division_code" varchar(10) NOT NULL, "disposition_type" text NOT NULL, "disposition_type_code" varchar(10) NOT NULL, "case_type_str" text NOT NULL, "case_type_code" varchar(10) NOT NULL, "case_name" text NOT NULL, "judge_code" varchar(10) NOT NULL, "judge_name" text NOT NULL, "courthouse_name" text NOT NULL, "date_status" timestamp with time zone NULL, "status_code" varchar(20) NOT NULL, "status_str" text NOT NULL);
--
-- Create model DocumentFiled
--
CREATE TABLE "lasc_documentfiled" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_filed" timestamp with time zone NOT NULL, "memo" text NOT NULL, "document_type" text NOT NULL, "party_str" text NOT NULL, "docket_id" integer NOT NULL);
--
-- Create model DocumentImage
--
CREATE TABLE "lasc_documentimage" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_processed" timestamp with time zone NULL, "date_filed" timestamp with time zone NULL, "doc_id" varchar(30) NOT NULL, "page_count" integer NULL, "document_type" text NOT NULL, "document_type_code" varchar(20) NOT NULL, "image_type_id" varchar(20) NOT NULL, "app_id" text NOT NULL, "odyssey_id" text NOT NULL, "is_downloadable" boolean NOT NULL, "security_level" varchar(10) NOT NULL, "description" text NOT NULL, "volume" text NOT NULL, "doc_part" text NOT NULL, "is_available" boolean NOT NULL, "docket_id" integer NOT NULL);
--
-- Create model LASCJSON
--
CREATE TABLE "lasc_lascjson" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "object_id" integer NOT NULL CHECK ("object_id" >= 0), "filepath" varchar(150) NOT NULL, "upload_type" smallint NOT NULL, "sha1" varchar(128) NOT NULL, "content_type_id" integer NOT NULL);
--
-- Create model LASCPDF
--
CREATE TABLE "lasc_lascpdf" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "sha1" varchar(40) NOT NULL, "page_count" integer NULL, "file_size" integer NULL, "filepath_local" varchar(1000) NOT NULL, "filepath_ia" varchar(1000) NOT NULL, "ia_upload_failure_count" smallint NULL, "thumbnail" varchar(100) NULL, "thumbnail_status" smallint NOT NULL, "plain_text" text NOT NULL, "ocr_status" smallint NULL, "object_id" integer NOT NULL CHECK ("object_id" >= 0), "content_type_id" integer NOT NULL);
--
-- Create model Party
--
CREATE TABLE "lasc_party" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "attorney_name" text NOT NULL, "attorney_firm" text NOT NULL, "entity_number" text NOT NULL, "party_name" text NOT NULL, "party_flag" text NOT NULL, "party_type_code" text NOT NULL, "party_description" text NOT NULL, "docket_id" integer NOT NULL);
--
-- Create model Proceeding
--
CREATE TABLE "lasc_proceeding" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "past_or_future" smallint NULL, "date_proceeding" timestamp with time zone NOT NULL, "proceeding_time" text NOT NULL, "am_pm" text NOT NULL, "memo" text NOT NULL, "courthouse_name" text NOT NULL, "address" text NOT NULL, "proceeding_room" text NOT NULL, "result" text NOT NULL, "judge_name" text NOT NULL, "event" text NOT NULL, "docket_id" integer NOT NULL);
--
-- Create model QueuedCase
--
CREATE TABLE "lasc_queuedcase" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "internal_case_id" varchar(300) NOT NULL, "judge_code" varchar(10) NOT NULL, "case_type_code" varchar(10) NOT NULL);
--
-- Create model QueuedPDF
--
CREATE TABLE "lasc_queuedpdf" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "internal_case_id" varchar(300) NOT NULL, "document_id" varchar(40) NOT NULL);
--
-- Create model TentativeRuling
--
CREATE TABLE "lasc_tentativeruling" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_creation" timestamp with time zone NULL, "date_hearing" timestamp with time zone NULL, "department" text NOT NULL, "ruling" text NOT NULL, "docket_id" integer NOT NULL);
--
-- Alter index_together for docket (1 constraint(s))
--
CREATE INDEX "lasc_docket_docket_number_district_division_code_07584433_idx" ON "lasc_docket" ("docket_number", "district", "division_code");
--
-- Add field docket to crossreference
--
ALTER TABLE "lasc_crossreference" ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field docket to action
--
ALTER TABLE "lasc_action" ADD COLUMN "docket_id" integer NOT NULL;
CREATE INDEX "lasc_action_date_created_4b47e989" ON "lasc_action" ("date_created");
CREATE INDEX "lasc_action_date_modified_1abed903" ON "lasc_action" ("date_modified");
CREATE INDEX "lasc_crossreference_date_created_fd96ff13" ON "lasc_crossreference" ("date_created");
CREATE INDEX "lasc_crossreference_date_modified_25a5050e" ON "lasc_crossreference" ("date_modified");
CREATE INDEX "lasc_docket_date_created_0046364b" ON "lasc_docket" ("date_created");
CREATE INDEX "lasc_docket_date_modified_1185b783" ON "lasc_docket" ("date_modified");
CREATE INDEX "lasc_docket_date_checked_266e9264" ON "lasc_docket" ("date_checked");
CREATE INDEX "lasc_docket_docket_number_0cb1db11" ON "lasc_docket" ("docket_number");
CREATE INDEX "lasc_docket_docket_number_0cb1db11_like" ON "lasc_docket" ("docket_number" varchar_pattern_ops);
ALTER TABLE "lasc_documentfiled" ADD CONSTRAINT "lasc_documentfiled_docket_id_ae29caa0_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_documentfiled_date_created_6b2a89bb" ON "lasc_documentfiled" ("date_created");
CREATE INDEX "lasc_documentfiled_date_modified_cc6080c9" ON "lasc_documentfiled" ("date_modified");
CREATE INDEX "lasc_documentfiled_docket_id_ae29caa0" ON "lasc_documentfiled" ("docket_id");
ALTER TABLE "lasc_documentimage" ADD CONSTRAINT "lasc_documentimage_docket_id_0b435bed_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_documentimage_date_created_0f0e5cb0" ON "lasc_documentimage" ("date_created");
CREATE INDEX "lasc_documentimage_date_modified_3426d953" ON "lasc_documentimage" ("date_modified");
CREATE INDEX "lasc_documentimage_docket_id_0b435bed" ON "lasc_documentimage" ("docket_id");
ALTER TABLE "lasc_lascjson" ADD CONSTRAINT "lasc_lascjson_content_type_id_f929a00e_fk_django_co" FOREIGN KEY ("content_type_id") REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_lascjson_date_created_c4be2182" ON "lasc_lascjson" ("date_created");
CREATE INDEX "lasc_lascjson_date_modified_69edb721" ON "lasc_lascjson" ("date_modified");
CREATE INDEX "lasc_lascjson_content_type_id_f929a00e" ON "lasc_lascjson" ("content_type_id");
ALTER TABLE "lasc_lascpdf" ADD CONSTRAINT "lasc_lascpdf_content_type_id_92b2954d_fk_django_content_type_id" FOREIGN KEY ("content_type_id") REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_lascpdf_date_created_01f9451f" ON "lasc_lascpdf" ("date_created");
CREATE INDEX "lasc_lascpdf_date_modified_37f39ca4" ON "lasc_lascpdf" ("date_modified");
CREATE INDEX "lasc_lascpdf_filepath_local_c10c8db5" ON "lasc_lascpdf" ("filepath_local");
CREATE INDEX "lasc_lascpdf_filepath_local_c10c8db5_like" ON "lasc_lascpdf" ("filepath_local" varchar_pattern_ops);
CREATE INDEX "lasc_lascpdf_content_type_id_92b2954d" ON "lasc_lascpdf" ("content_type_id");
ALTER TABLE "lasc_party" ADD CONSTRAINT "lasc_party_docket_id_eefccc6e_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_party_date_created_ac942438" ON "lasc_party" ("date_created");
CREATE INDEX "lasc_party_date_modified_a3c545ea" ON "lasc_party" ("date_modified");
CREATE INDEX "lasc_party_docket_id_eefccc6e" ON "lasc_party" ("docket_id");
ALTER TABLE "lasc_proceeding" ADD CONSTRAINT "lasc_proceeding_docket_id_5722e146_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_proceeding_date_created_f283822f" ON "lasc_proceeding" ("date_created");
CREATE INDEX "lasc_proceeding_date_modified_c0959a18" ON "lasc_proceeding" ("date_modified");
CREATE INDEX "lasc_proceeding_docket_id_5722e146" ON "lasc_proceeding" ("docket_id");
CREATE INDEX "lasc_queuedcase_date_created_d0bc8b3c" ON "lasc_queuedcase" ("date_created");
CREATE INDEX "lasc_queuedcase_date_modified_74609387" ON "lasc_queuedcase" ("date_modified");
CREATE INDEX "lasc_queuedcase_internal_case_id_9e5b0a54" ON "lasc_queuedcase" ("internal_case_id");
CREATE INDEX "lasc_queuedcase_internal_case_id_9e5b0a54_like" ON "lasc_queuedcase" ("internal_case_id" varchar_pattern_ops);
CREATE INDEX "lasc_queuedpdf_date_created_7ed0bfc0" ON "lasc_queuedpdf" ("date_created");
CREATE INDEX "lasc_queuedpdf_date_modified_ed856b05" ON "lasc_queuedpdf" ("date_modified");
CREATE INDEX "lasc_queuedpdf_internal_case_id_ceffd139" ON "lasc_queuedpdf" ("internal_case_id");
CREATE INDEX "lasc_queuedpdf_internal_case_id_ceffd139_like" ON "lasc_queuedpdf" ("internal_case_id" varchar_pattern_ops);
CREATE INDEX "lasc_queuedpdf_document_id_5ef0503b" ON "lasc_queuedpdf" ("document_id");
CREATE INDEX "lasc_queuedpdf_document_id_5ef0503b_like" ON "lasc_queuedpdf" ("document_id" varchar_pattern_ops);
ALTER TABLE "lasc_tentativeruling" ADD CONSTRAINT "lasc_tentativeruling_docket_id_51a63aa6_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_tentativeruling_date_created_577564e9" ON "lasc_tentativeruling" ("date_created");
CREATE INDEX "lasc_tentativeruling_date_modified_11fea074" ON "lasc_tentativeruling" ("date_modified");
CREATE INDEX "lasc_tentativeruling_docket_id_51a63aa6" ON "lasc_tentativeruling" ("docket_id");
CREATE INDEX "lasc_crossreference_docket_id_1078b88c" ON "lasc_crossreference" ("docket_id");
ALTER TABLE "lasc_crossreference" ADD CONSTRAINT "lasc_crossreference_docket_id_1078b88c_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "lasc_action_docket_id_97937003" ON "lasc_action" ("docket_id");
ALTER TABLE "lasc_action" ADD CONSTRAINT "lasc_action_docket_id_97937003_fk_lasc_docket_id" FOREIGN KEY ("docket_id") REFERENCES "lasc_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
