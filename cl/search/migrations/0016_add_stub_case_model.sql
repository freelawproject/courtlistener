BEGIN;
--
-- Create model OpinionStub
--
CREATE TABLE "search_opinionstub" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "case_name" text NOT NULL, "case_name_full" text NOT NULL, "date_filed" date NULL, "date_decided" date NULL, "date_argued" date NULL, "date_revised" date NULL, "court_str" text NOT NULL, "docket_number" text NOT NULL, "citations_str" text NOT NULL, "citations" jsonb NULL, "court_id" varchar(15) NULL);
ALTER TABLE "search_opinionstub" ADD CONSTRAINT "search_opinionstub_court_id_e7a731cf_fk_search_court_id" FOREIGN KEY ("court_id") REFERENCES "search_court" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinionstub_date_created_f97310f7" ON "search_opinionstub" ("date_created");
CREATE INDEX "search_opinionstub_date_modified_4c2267ac" ON "search_opinionstub" ("date_modified");
CREATE INDEX "search_opinionstub_court_id_e7a731cf" ON "search_opinionstub" ("court_id");
CREATE INDEX "search_opinionstub_court_id_e7a731cf_like" ON "search_opinionstub" ("court_id" varchar_pattern_ops);
COMMIT;
