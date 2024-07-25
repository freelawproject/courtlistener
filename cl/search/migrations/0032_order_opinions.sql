BEGIN;
--
-- Remove trigger update_or_delete_snapshot_delete from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_1f4fd ON "search_opinion";
--
-- Remove trigger update_or_delete_snapshot_update from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_67ecd ON "search_opinion";
--
-- Add field order to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "order" integer NULL;
--
-- Add field order to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "order" integer NULL;
--
-- Create trigger update_or_delete_snapshot_update on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_67ecd()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "html_with_citations", "id", "joined_by_str", "local_path", "order", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (OLD."author_id", OLD."author_str", OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."download_url", OLD."extracted_by_ocr", OLD."html", OLD."html_anon_2020", OLD."html_columbia", OLD."html_lawbox", OLD."html_with_citations", OLD."id", OLD."joined_by_str", OLD."local_path", OLD."order", OLD."page_count", OLD."per_curiam", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."plain_text", OLD."sha1", OLD."type", OLD."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_67ecd ON "search_opinion";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_67ecd
                AFTER UPDATE ON "search_opinion"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."cluster_id" IS DISTINCT FROM (NEW."cluster_id") OR OLD."author_id" IS DISTINCT FROM (NEW."author_id") OR OLD."author_str" IS DISTINCT FROM (NEW."author_str") OR OLD."per_curiam" IS DISTINCT FROM (NEW."per_curiam") OR OLD."joined_by_str" IS DISTINCT FROM (NEW."joined_by_str") OR OLD."type" IS DISTINCT FROM (NEW."type") OR OLD."sha1" IS DISTINCT FROM (NEW."sha1") OR OLD."page_count" IS DISTINCT FROM (NEW."page_count") OR OLD."download_url" IS DISTINCT FROM (NEW."download_url") OR OLD."local_path" IS DISTINCT FROM (NEW."local_path") OR OLD."plain_text" IS DISTINCT FROM (NEW."plain_text") OR OLD."html" IS DISTINCT FROM (NEW."html") OR OLD."html_lawbox" IS DISTINCT FROM (NEW."html_lawbox") OR OLD."html_columbia" IS DISTINCT FROM (NEW."html_columbia") OR OLD."html_anon_2020" IS DISTINCT FROM (NEW."html_anon_2020") OR OLD."xml_harvard" IS DISTINCT FROM (NEW."xml_harvard") OR OLD."html_with_citations" IS DISTINCT FROM (NEW."html_with_citations") OR OLD."extracted_by_ocr" IS DISTINCT FROM (NEW."extracted_by_ocr") OR OLD."order" IS DISTINCT FROM (NEW."order"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_67ecd();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_67ecd ON "search_opinion" IS '89fec08f03e567ec8ecc7cd1e8ec5f665abf9d3b';
        
--
-- Create trigger update_or_delete_snapshot_delete on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_1f4fd()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "html_with_citations", "id", "joined_by_str", "local_path", "order", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (OLD."author_id", OLD."author_str", OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."download_url", OLD."extracted_by_ocr", OLD."html", OLD."html_anon_2020", OLD."html_columbia", OLD."html_lawbox", OLD."html_with_citations", OLD."id", OLD."joined_by_str", OLD."local_path", OLD."order", OLD."page_count", OLD."per_curiam", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."plain_text", OLD."sha1", OLD."type", OLD."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_1f4fd ON "search_opinion";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_delete_1f4fd
                AFTER DELETE ON "search_opinion"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_1f4fd();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_1f4fd ON "search_opinion" IS '79bebd7cda3c6ed3bc40f28799cf9c0f2638e2ad';
        
--
-- Create constraint unique_opinion_order on model opinion
--
ALTER TABLE "search_opinion" ADD CONSTRAINT "unique_opinion_order" UNIQUE ("cluster_id", "order");
COMMIT;
