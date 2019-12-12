BEGIN;
--
-- Create model PacerFetchQueue
--
CREATE TABLE "recap_pacerfetchqueue" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_completed" timestamp with time zone NULL, "status" smallint NOT NULL, "request_type" smallint NOT NULL, "message" text NOT NULL, "pacer_case_id" varchar(100) NOT NULL, "docket_number" varchar(50) NOT NULL, "de_date_start" date NULL, "de_date_end" date NULL, "de_number_start" integer NULL, "de_number_end" integer NULL, "show_parties_and_counsel" boolean NOT NULL, "show_terminated_parties" boolean NOT NULL, "show_list_of_member_cases" boolean NOT NULL, "court_id" varchar(15) NULL, "docket_id" integer NULL, "recap_document_id" integer NULL, "user_id" integer NOT NULL);
ALTER TABLE "recap_pacerfetchqueue" ADD CONSTRAINT "recap_pacerfetchqueue_court_id_1246ddd3_fk_search_court_id" FOREIGN KEY ("court_id") REFERENCES "search_court" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "recap_pacerfetchqueue" ADD CONSTRAINT "recap_pacerfetchqueue_docket_id_371bfcf0_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "recap_pacerfetchqueue" ADD CONSTRAINT "recap_pacerfetchqueu_recap_document_id_b9c23829_fk_search_re" FOREIGN KEY ("recap_document_id") REFERENCES "search_recapdocument" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "recap_pacerfetchqueue" ADD CONSTRAINT "recap_pacerfetchqueue_user_id_a2c0c6f8_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "recap_pacerfetchqueue_date_created_e21b4d2e" ON "recap_pacerfetchqueue" ("date_created");
CREATE INDEX "recap_pacerfetchqueue_date_modified_d110c824" ON "recap_pacerfetchqueue" ("date_modified");
CREATE INDEX "recap_pacerfetchqueue_date_completed_cfc17415" ON "recap_pacerfetchqueue" ("date_completed");
CREATE INDEX "recap_pacerfetchqueue_status_19964cb1" ON "recap_pacerfetchqueue" ("status");
CREATE INDEX "recap_pacerfetchqueue_pacer_case_id_21aa36c3" ON "recap_pacerfetchqueue" ("pacer_case_id");
CREATE INDEX "recap_pacerfetchqueue_pacer_case_id_21aa36c3_like" ON "recap_pacerfetchqueue" ("pacer_case_id" varchar_pattern_ops);
CREATE INDEX "recap_pacerfetchqueue_court_id_1246ddd3" ON "recap_pacerfetchqueue" ("court_id");
CREATE INDEX "recap_pacerfetchqueue_court_id_1246ddd3_like" ON "recap_pacerfetchqueue" ("court_id" varchar_pattern_ops);
CREATE INDEX "recap_pacerfetchqueue_docket_id_371bfcf0" ON "recap_pacerfetchqueue" ("docket_id");
CREATE INDEX "recap_pacerfetchqueue_recap_document_id_b9c23829" ON "recap_pacerfetchqueue" ("recap_document_id");
CREATE INDEX "recap_pacerfetchqueue_user_id_a2c0c6f8" ON "recap_pacerfetchqueue" ("user_id");
COMMIT;
