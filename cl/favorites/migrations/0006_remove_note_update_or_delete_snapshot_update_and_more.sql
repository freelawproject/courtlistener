BEGIN;
--
-- Remove trigger update_or_delete_snapshot_update from model note
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ed3a1 ON "favorites_note";
--
-- Remove trigger update_or_delete_snapshot_update from model usertag
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_9deec ON "favorites_usertag";
--
-- Create trigger update_or_delete_snapshot_update on model note
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_ed3a1()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "date_created", "date_modified", "docket_id_id", "id", "name", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_doc_id_id", "user_id") VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id", OLD."id", OLD."name", OLD."notes", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."recap_doc_id_id", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ed3a1 ON "favorites_note";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_ed3a1
                AFTER UPDATE ON "favorites_note"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."cluster_id_id" IS DISTINCT FROM (NEW."cluster_id_id") OR OLD."audio_id_id" IS DISTINCT FROM (NEW."audio_id_id") OR OLD."docket_id_id" IS DISTINCT FROM (NEW."docket_id_id") OR OLD."recap_doc_id_id" IS DISTINCT FROM (NEW."recap_doc_id_id") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."notes" IS DISTINCT FROM (NEW."notes"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_ed3a1();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_ed3a1 ON "favorites_note" IS '9731e3216c6d227dcc5c11083309a6318e0f9499';
        
--
-- Create trigger update_or_delete_snapshot_update on model usertag
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_9deec()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified", "description", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "published", "title", "user_id") VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."published", OLD."title", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_9deec ON "favorites_usertag";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_9deec
                AFTER UPDATE ON "favorites_usertag"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."title" IS DISTINCT FROM (NEW."title") OR OLD."description" IS DISTINCT FROM (NEW."description") OR OLD."published" IS DISTINCT FROM (NEW."published"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_9deec();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_9deec ON "favorites_usertag" IS '680021ed57671af8d431e0fcc2fa28af576df12e';
        
COMMIT;
