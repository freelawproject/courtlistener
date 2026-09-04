BEGIN;
--
-- Remove trigger update_update from model nycoadocument
--
DROP TRIGGER IF EXISTS pgtrigger_update_update_8efbf ON "search_nycoadocument";
--
-- Remove trigger delete_delete from model nycoadocument
--
DROP TRIGGER IF EXISTS pgtrigger_delete_delete_d8581 ON "search_nycoadocument";
--
-- Add field sha256 to nycoadocument
--
ALTER TABLE "search_nycoadocument" ADD COLUMN "sha256" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_nycoadocument" ALTER COLUMN "sha256" DROP DEFAULT;
COMMENT ON COLUMN "search_nycoadocument"."sha256" IS 'Hex digest of the file, as the scraper hashed it on the way to storage. Empty for a file no scrape has fetched. This is what tells a file the Court has corrected from the one already published, and the inherited `sha1` stays empty in its favour, because nothing on this model''s path ever reads the bytes; see `make_filename`.';
--
-- Add field sha256 to nycoadocumentevent
--
ALTER TABLE "search_nycoadocumentevent" ADD COLUMN "sha256" varchar(64) DEFAULT '' NOT NULL;
ALTER TABLE "search_nycoadocumentevent" ALTER COLUMN "sha256" DROP DEFAULT;
COMMENT ON COLUMN "search_nycoadocumentevent"."sha256" IS 'Hex digest of the file, as the scraper hashed it on the way to storage. Empty for a file no scrape has fetched. This is what tells a file the Court has corrected from the one already published, and the inherited `sha1` stays empty in its favour, because nothing on this model''s path ever reads the bytes; see `make_filename`.';
--
-- Create trigger update_update on model nycoadocument
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_update_8efbf()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_nycoadocumentevent" ("available", "content_type", "date_created", "date_modified", "doc_party", "doc_role", "doc_type", "docket_entry_id", "file_name", "file_size", "filepath_ia", "filepath_local", "ia_upload_failure_count", "id", "ocr_status", "page_count", "part", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "processing_error", "sha1", "sha256", "thumbnail", "thumbnail_status", "volume") VALUES (OLD."available", OLD."content_type", OLD."date_created", OLD."date_modified", OLD."doc_party", OLD."doc_role", OLD."doc_type", OLD."docket_entry_id", OLD."file_name", OLD."file_size", OLD."filepath_ia", OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id", OLD."ocr_status", OLD."page_count", OLD."part", _pgh_attach_context(), NOW(), 'update', OLD."id", OLD."plain_text", OLD."processing_error", OLD."sha1", OLD."sha256", OLD."thumbnail", OLD."thumbnail_status", OLD."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_update_8efbf ON "search_nycoadocument";
            CREATE  TRIGGER pgtrigger_update_update_8efbf
                AFTER UPDATE ON "search_nycoadocument"
                
                
                FOR EACH ROW WHEN (OLD."available" IS DISTINCT FROM (NEW."available") OR OLD."content_type" IS DISTINCT FROM (NEW."content_type") OR OLD."doc_party" IS DISTINCT FROM (NEW."doc_party") OR OLD."doc_role" IS DISTINCT FROM (NEW."doc_role") OR OLD."doc_type" IS DISTINCT FROM (NEW."doc_type") OR OLD."docket_entry_id" IS DISTINCT FROM (NEW."docket_entry_id") OR OLD."file_name" IS DISTINCT FROM (NEW."file_name") OR OLD."file_size" IS DISTINCT FROM (NEW."file_size") OR OLD."filepath_ia" IS DISTINCT FROM (NEW."filepath_ia") OR OLD."filepath_local" IS DISTINCT FROM (NEW."filepath_local") OR OLD."ia_upload_failure_count" IS DISTINCT FROM (NEW."ia_upload_failure_count") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."ocr_status" IS DISTINCT FROM (NEW."ocr_status") OR OLD."page_count" IS DISTINCT FROM (NEW."page_count") OR OLD."part" IS DISTINCT FROM (NEW."part") OR OLD."plain_text" IS DISTINCT FROM (NEW."plain_text") OR OLD."processing_error" IS DISTINCT FROM (NEW."processing_error") OR OLD."sha1" IS DISTINCT FROM (NEW."sha1") OR OLD."sha256" IS DISTINCT FROM (NEW."sha256") OR OLD."thumbnail" IS DISTINCT FROM (NEW."thumbnail") OR OLD."thumbnail_status" IS DISTINCT FROM (NEW."thumbnail_status") OR OLD."volume" IS DISTINCT FROM (NEW."volume"))
                EXECUTE PROCEDURE pgtrigger_update_update_8efbf();

            COMMENT ON TRIGGER pgtrigger_update_update_8efbf ON "search_nycoadocument" IS '2bb18ea26e9aa5e30687be403da80bb495b91047';
        
--
-- Create trigger delete_delete on model nycoadocument
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

            CREATE OR REPLACE FUNCTION pgtrigger_delete_delete_d8581()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_nycoadocumentevent" ("available", "content_type", "date_created", "date_modified", "doc_party", "doc_role", "doc_type", "docket_entry_id", "file_name", "file_size", "filepath_ia", "filepath_local", "ia_upload_failure_count", "id", "ocr_status", "page_count", "part", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "processing_error", "sha1", "sha256", "thumbnail", "thumbnail_status", "volume") VALUES (OLD."available", OLD."content_type", OLD."date_created", OLD."date_modified", OLD."doc_party", OLD."doc_role", OLD."doc_type", OLD."docket_entry_id", OLD."file_name", OLD."file_size", OLD."filepath_ia", OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id", OLD."ocr_status", OLD."page_count", OLD."part", _pgh_attach_context(), NOW(), 'delete', OLD."id", OLD."plain_text", OLD."processing_error", OLD."sha1", OLD."sha256", OLD."thumbnail", OLD."thumbnail_status", OLD."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_delete_delete_d8581 ON "search_nycoadocument";
            CREATE  TRIGGER pgtrigger_delete_delete_d8581
                AFTER DELETE ON "search_nycoadocument"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_delete_delete_d8581();

            COMMENT ON TRIGGER pgtrigger_delete_delete_d8581 ON "search_nycoadocument" IS '387d96e2c4c767c40c0310cc23417cb93f3be419';
        
COMMIT;
