BEGIN;
--
-- Add field acms_document_guid to recapdocument
--
ALTER TABLE "search_recapdocument" ADD COLUMN "acms_document_guid" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocument" ALTER COLUMN "acms_document_guid" DROP DEFAULT;
--
-- Add field acms_document_guid to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent" ADD COLUMN "acms_document_guid" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocumentevent" ALTER COLUMN "acms_document_guid" DROP DEFAULT;
--
-- Alter field pacer_case_id on claimhistory
--
-- (no-op)
--
-- Alter field pacer_doc_id on claimhistory
--
ALTER TABLE "search_claimhistory" ALTER COLUMN "pacer_doc_id" TYPE varchar(64);
CREATE INDEX "search_claimhistory_pacer_doc_id_ddcc4bdf" ON "search_claimhistory" ("pacer_doc_id");
CREATE INDEX "search_claimhistory_pacer_doc_id_ddcc4bdf_like" ON "search_claimhistory" ("pacer_doc_id" varchar_pattern_ops);
--
-- Alter field pacer_case_id on claimhistoryevent
--
-- (no-op)
--
-- Alter field pacer_doc_id on claimhistoryevent
--
ALTER TABLE "search_claimhistoryevent" ALTER COLUMN "pacer_doc_id" TYPE varchar(64);
--
-- Alter field pacer_case_id on docket
--
-- (no-op)
--
-- Alter field pacer_case_id on docketevent
--
-- (no-op)
--
-- Alter field pacer_doc_id on recapdocument
--
ALTER TABLE "search_recapdocument" ALTER COLUMN "pacer_doc_id" TYPE varchar(64);
CREATE INDEX "search_recapdocument_pacer_doc_id_e52314d9" ON "search_recapdocument" ("pacer_doc_id");
CREATE INDEX "search_recapdocument_pacer_doc_id_e52314d9_like" ON "search_recapdocument" ("pacer_doc_id" varchar_pattern_ops);
--
-- Alter field pacer_doc_id on recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent" ALTER COLUMN "pacer_doc_id" TYPE varchar(64);
--
-- Create index search_reca_acms_do_17c11f_idx on field(s) acms_document_guid of model recapdocument
--
CREATE INDEX "search_reca_acms_do_17c11f_idx" ON "search_recapdocument" ("acms_document_guid");

COMMIT;
