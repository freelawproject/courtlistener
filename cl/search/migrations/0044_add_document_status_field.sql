
BEGIN;
--
-- Remove trigger update_update from model recapdocument
--
DROP TRIGGER IF EXISTS pgtrigger_update_update_af6ad ON "search_recapdocument";
--
-- Remove trigger delete_delete from model recapdocument
--
DROP TRIGGER IF EXISTS pgtrigger_delete_delete_28a84 ON "search_recapdocument";
--
-- Add field document_status to recapdocument
--
ALTER TABLE "search_recapdocument" ADD COLUMN "document_status" text DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocument" ALTER COLUMN "document_status" DROP DEFAULT;
--
-- Add field document_status to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent" ADD COLUMN "document_status" text DEFAULT '' NOT NULL;
ALTER TABLE "search_recapdocumentevent" ALTER COLUMN "document_status" DROP DEFAULT;
--
-- Create trigger update_update on model recapdocument
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_update_update_af6ad()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_recapdocumentevent" ("acms_document_guid", "attachment_number", "date_created", "date_modified", "date_upload", "description", "docket_entry_id", "document_number", "document_status", "document_type", "file_size", "filepath_ia", "filepath_local", "ia_upload_failure_count", "id", "is_available", "is_free_on_pacer", "is_sealed", "ocr_status", "pacer_doc_id", "page_count", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "thumbnail", "thumbnail_status") VALUES (OLD."acms_document_guid", OLD."attachment_number", OLD."date_created", OLD."date_modified", OLD."date_upload", OLD."description", OLD."docket_entry_id", OLD."document_number", OLD."document_status", OLD."document_type", OLD."file_size", OLD."filepath_ia", OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id", OLD."is_available", OLD."is_free_on_pacer", OLD."is_sealed", OLD."ocr_status", OLD."pacer_doc_id", OLD."page_count", _pgh_attach_context(), NOW(), 'update', OLD."id", OLD."plain_text", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_update_af6ad ON "search_recapdocument";
            CREATE  TRIGGER pgtrigger_update_update_af6ad
                AFTER UPDATE ON "search_recapdocument"


                FOR EACH ROW WHEN (OLD."acms_document_guid" IS DISTINCT FROM (NEW."acms_document_guid") OR OLD."attachment_number" IS DISTINCT FROM (NEW."attachment_number") OR OLD."date_upload" IS DISTINCT FROM (NEW."date_upload") OR OLD."description" IS DISTINCT FROM (NEW."description") OR OLD."docket_entry_id" IS DISTINCT FROM (NEW."docket_entry_id") OR OLD."document_number" IS DISTINCT FROM (NEW."document_number") OR OLD."document_status" IS DISTINCT FROM (NEW."document_status") OR OLD."document_type" IS DISTINCT FROM (NEW."document_type") OR OLD."file_size" IS DISTINCT FROM (NEW."file_size") OR OLD."filepath_ia" IS DISTINCT FROM (NEW."filepath_ia") OR OLD."filepath_local" IS DISTINCT FROM (NEW."filepath_local") OR OLD."ia_upload_failure_count" IS DISTINCT FROM (NEW."ia_upload_failure_count") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."is_available" IS DISTINCT FROM (NEW."is_available") OR OLD."is_free_on_pacer" IS DISTINCT FROM (NEW."is_free_on_pacer") OR OLD."is_sealed" IS DISTINCT FROM (NEW."is_sealed") OR OLD."ocr_status" IS DISTINCT FROM (NEW."ocr_status") OR OLD."pacer_doc_id" IS DISTINCT FROM (NEW."pacer_doc_id") OR OLD."page_count" IS DISTINCT FROM (NEW."page_count") OR OLD."plain_text" IS DISTINCT FROM (NEW."plain_text") OR OLD."sha1" IS DISTINCT FROM (NEW."sha1") OR OLD."thumbnail" IS DISTINCT FROM (NEW."thumbnail") OR OLD."thumbnail_status" IS DISTINCT FROM (NEW."thumbnail_status"))      
                EXECUTE PROCEDURE pgtrigger_update_update_af6ad();

            COMMENT ON TRIGGER pgtrigger_update_update_af6ad ON "search_recapdocument" IS 'e82056218a8fa8a7e1ec355021a787ab507669a8';

--
-- Create trigger delete_delete on model recapdocument
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_delete_delete_28a84()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_recapdocumentevent" ("acms_document_guid", "attachment_number", "date_created", "date_modified", "date_upload", "description", "docket_entry_id", "document_number", "document_status", "document_type", "file_size", "filepath_ia", "filepath_local", "ia_upload_failure_count", "id", "is_available", "is_free_on_pacer", "is_sealed", "ocr_status", "pacer_doc_id", "page_count", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "thumbnail", "thumbnail_status") VALUES (OLD."acms_document_guid", OLD."attachment_number", OLD."date_created", OLD."date_modified", OLD."date_upload", OLD."description", OLD."docket_entry_id", OLD."document_number", OLD."document_status", OLD."document_type", OLD."file_size", OLD."filepath_ia", OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id", OLD."is_available", OLD."is_free_on_pacer", OLD."is_sealed", OLD."ocr_status", OLD."pacer_doc_id", OLD."page_count", _pgh_attach_context(), NOW(), 'delete', OLD."id", OLD."plain_text", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_delete_delete_28a84 ON "search_recapdocument";
            CREATE  TRIGGER pgtrigger_delete_delete_28a84
                AFTER DELETE ON "search_recapdocument"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_delete_delete_28a84();

            COMMENT ON TRIGGER pgtrigger_delete_delete_28a84 ON "search_recapdocument" IS '22effbe6b744ec7f1e48dea46f2ccd657fd8706a';

COMMIT;