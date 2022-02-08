-- This one is a bit weird. We didn't make SQL files for migrations 1-3 b/c
-- we squashed their migrations after they were migrated in prod, but before
-- they were migrated in the replica. As a result, the recap email queue didn't
-- get created properly. This migration fixes that and should be run before
-- 0004.

BEGIN;
--
-- FROM 0001
--
-- Create model EmailProcessingQueue
--
CREATE TABLE "recap_emailprocessingqueue" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "filepath" varchar(300) NULL, "status" smallint NOT NULL, "status_message" text NOT NULL);

CREATE INDEX "recap_emailprocessingqueue_date_created_2f32c34d" ON "recap_emailprocessingqueue" ("date_created");
CREATE INDEX "recap_emailprocessingqueue_date_modified_0900d415" ON "recap_emailprocessingqueue" ("date_modified");
CREATE INDEX "recap_emailprocessingqueue_status_798f5968" ON "recap_emailprocessingqueue" ("status");


--
-- FROM 0002
--
-- Add field court to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "court_id" varchar(15) NOT NULL CONSTRAINT "recap_emailprocessingqueue_court_id_83f67bf3_fk_search_court_id" REFERENCES "search_court"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "recap_emailprocessingqueue_court_id_83f67bf3_fk_search_court_id" IMMEDIATE;
--
-- Add field recap_documents to emailprocessingqueue
--
CREATE TABLE "recap_emailprocessingqueue_recap_documents" ("id" serial NOT NULL PRIMARY KEY, "emailprocessingqueue_id" integer NOT NULL, "recapdocument_id" integer NOT NULL);
--
-- Add field uploader to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "uploader_id" integer NOT NULL CONSTRAINT "recap_emailprocessingqueue_uploader_id_32651a93_fk_auth_user_id" REFERENCES "auth_user"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "recap_emailprocessingqueue_uploader_id_32651a93_fk_auth_user_id" IMMEDIATE;
CREATE INDEX "recap_emailprocessingqueue_court_id_83f67bf3" ON "recap_emailprocessingqueue" ("court_id");
CREATE INDEX "recap_emailprocessingqueue_court_id_83f67bf3_like" ON "recap_emailprocessingqueue" ("court_id" varchar_pattern_ops);
ALTER TABLE "recap_emailprocessingqueue_recap_documents" ADD CONSTRAINT "recap_emailprocessingque_emailprocessingqueue_id__25151718_uniq" UNIQUE ("emailprocessingqueue_id", "recapdocument_id");
ALTER TABLE "recap_emailprocessingqueue_recap_documents" ADD CONSTRAINT "recap_emailprocessin_emailprocessingqueue_896acbad_fk_recap_ema" FOREIGN KEY ("emailprocessingqueue_id") REFERENCES "recap_emailprocessingqueue" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "recap_emailprocessingqueue_recap_documents" ADD CONSTRAINT "recap_emailprocessin_recapdocument_id_66e16cbf_fk_search_re" FOREIGN KEY ("recapdocument_id") REFERENCES "search_recapdocument" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "recap_emailprocessingqueue_emailprocessingqueue_id_896acbad" ON "recap_emailprocessingqueue_recap_documents" ("emailprocessingqueue_id");
CREATE INDEX "recap_emailprocessingqueue_recapdocument_id_66e16cbf" ON "recap_emailprocessingqueue_recap_documents" ("recapdocument_id");
CREATE INDEX "recap_emailprocessingqueue_uploader_id_32651a93" ON "recap_emailprocessingqueue" ("uploader_id");


--
-- FROM 0003
--
--
-- Add field message_id to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "message_id" text NOT NULL;

COMMIT;
