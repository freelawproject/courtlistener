BEGIN;
--
-- Remove trigger update_update from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_update_update_24107 ON "search_opinion";
--
-- Remove trigger delete_delete from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_delete_delete_613d8 ON "search_opinion";
--
-- Remove field html_with_citations from opinionevent
--
ALTER TABLE "search_opinionevent" DROP COLUMN "html_with_citations" CASCADE;
--
-- Create trigger update_update on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_update_24107()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "id", "joined_by_str", "local_path", "ordering_key", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (OLD."author_id", OLD."author_str", OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."download_url", OLD."extracted_by_ocr", OLD."html", OLD."html_anon_2020", OLD."html_columbia", OLD."html_lawbox", OLD."id", OLD."joined_by_str", OLD."local_path", OLD."ordering_key", OLD."page_count", OLD."per_curiam", _pgh_attach_context(), NOW(), 'update', OLD."id", OLD."plain_text", OLD."sha1", OLD."type", OLD."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_update_24107 ON "search_opinion";
            CREATE  TRIGGER pgtrigger_update_update_24107
                AFTER UPDATE ON "search_opinion"


                FOR EACH ROW WHEN (OLD."author_id" IS DISTINCT FROM (NEW."author_id") OR OLD."author_str" IS DISTINCT FROM (NEW."author_str") OR OLD."cluster_id" IS DISTINCT FROM (NEW."cluster_id") OR OLD."download_url" IS DISTINCT FROM (NEW."download_url") OR OLD."extracted_by_ocr" IS DISTINCT FROM (NEW."extracted_by_ocr") OR OLD."html" IS DISTINCT FROM (NEW."html") OR OLD."html_anon_2020" IS DISTINCT FROM (NEW."html_anon_2020") OR OLD."html_columbia" IS DISTINCT FROM (NEW."html_columbia") OR OLD."html_lawbox" IS DISTINCT FROM (NEW."html_lawbox") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."joined_by_str" IS DISTINCT FROM (NEW."joined_by_str") OR OLD."local_path" IS DISTINCT FROM (NEW."local_path") OR OLD."ordering_key" IS DISTINCT FROM (NEW."ordering_key") OR OLD."page_count" IS DISTINCT FROM (NEW."page_count") OR OLD."per_curiam" IS DISTINCT FROM (NEW."per_curiam") OR OLD."plain_text" IS DISTINCT FROM (NEW."plain_text") OR OLD."sha1" IS DISTINCT FROM (NEW."sha1") OR OLD."type" IS DISTINCT FROM (NEW."type") OR OLD."xml_harvard" IS DISTINCT FROM (NEW."xml_harvard"))
                EXECUTE PROCEDURE pgtrigger_update_update_24107();

            COMMENT ON TRIGGER pgtrigger_update_update_24107 ON "search_opinion" IS '739ffa57687e941acba4beaeab50775ab12ab000';

--
-- Create trigger delete_delete on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_delete_delete_613d8()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "id", "joined_by_str", "local_path", "ordering_key", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (OLD."author_id", OLD."author_str", OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."download_url", OLD."extracted_by_ocr", OLD."html", OLD."html_anon_2020", OLD."html_columbia", OLD."html_lawbox", OLD."id", OLD."joined_by_str", OLD."local_path", OLD."ordering_key", OLD."page_count", OLD."per_curiam", _pgh_attach_context(), NOW(), 'delete', OLD."id", OLD."plain_text", OLD."sha1", OLD."type", OLD."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_delete_delete_613d8 ON "search_opinion";
            CREATE  TRIGGER pgtrigger_delete_delete_613d8
                AFTER DELETE ON "search_opinion"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_delete_delete_613d8();

            COMMENT ON TRIGGER pgtrigger_delete_delete_613d8 ON "search_opinion" IS 'a85ccccca2e440d3b2eec80fb6109bd69894ac0d';

COMMIT;