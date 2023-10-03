BEGIN;
--
-- Add field acms_document_guid to processingqueue
--
ALTER TABLE "recap_processingqueue" ADD COLUMN "acms_document_guid" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "recap_processingqueue" ALTER COLUMN "acms_document_guid" DROP DEFAULT;
--
-- Alter field upload_type on pacerhtmlfiles
--
-- (no-op)
--
-- Alter field pacer_case_id on processingqueue
--
-- (no-op)
--
-- Alter field pacer_doc_id on processingqueue
--
ALTER TABLE "recap_processingqueue" ALTER COLUMN "pacer_doc_id" TYPE varchar(64);
--
-- Alter field upload_type on processingqueue
--
-- (no-op)
--
-- Create index recap_proce_acms_do_2e7cae_idx on field(s) acms_document_guid of model processingqueue
--
CREATE INDEX "recap_proce_acms_do_2e7cae_idx" ON "recap_processingqueue" ("acms_document_guid");
COMMIT;
