BEGIN;
--
-- Remove trigger snapshot_insert from model dockettag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_d9def ON "favorites_dockettag";
--
-- Remove trigger snapshot_update from model dockettag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2cb4a ON "favorites_dockettag";
--
-- Remove trigger snapshot_insert from model note
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_7e480 ON "favorites_note";
--
-- Remove trigger snapshot_update from model note
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc74c ON "favorites_note";
--
-- Remove trigger snapshot_insert from model prayer
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_9becd ON "favorites_prayer";
--
-- Remove trigger snapshot_update from model prayer
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f75d ON "favorites_prayer";
--
-- Remove trigger snapshot_insert from model usertag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_38cf8 ON "favorites_usertag";
--
-- Remove trigger snapshot_update from model usertag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8ec9c ON "favorites_usertag";
--
-- Remove field status from prayerevent
--
ALTER TABLE "favorites_prayerevent" DROP COLUMN "status" CASCADE;
--
-- Create trigger custom_snapshot_update on model dockettag
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

            CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_c954a()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_dockettagevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "tag_id") VALUES (OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."tag_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_c954a ON "favorites_dockettag";
            CREATE  TRIGGER pgtrigger_custom_snapshot_update_c954a
                AFTER UPDATE ON "favorites_dockettag"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_c954a();

            COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_c954a ON "favorites_dockettag" IS '0d5e0dea082de5be16a88c01949c94c0769b4a8f';
        ;
--
-- Create trigger custom_snapshot_update on model note
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

            CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_f3950()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "date_created", "date_modified", "docket_id_id", "id", "name", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_doc_id_id", "user_id") VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id", OLD."id", OLD."name", OLD."notes", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."recap_doc_id_id", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_f3950 ON "favorites_note";
            CREATE  TRIGGER pgtrigger_custom_snapshot_update_f3950
                AFTER UPDATE ON "favorites_note"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."cluster_id_id" IS DISTINCT FROM NEW."cluster_id_id" OR OLD."audio_id_id" IS DISTINCT FROM NEW."audio_id_id" OR OLD."docket_id_id" IS DISTINCT FROM NEW."docket_id_id" OR OLD."recap_doc_id_id" IS DISTINCT FROM NEW."recap_doc_id_id" OR OLD."name" IS DISTINCT FROM NEW."name" OR OLD."notes" IS DISTINCT FROM NEW."notes")
                EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_f3950();

            COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_f3950 ON "favorites_note" IS 'd16a9903da4f7207e85cef197b16404ab23ab0b8';
        ;
--
-- Create trigger custom_snapshot_update on model prayer
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

            CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_2ec38()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_prayerevent" ("date_created", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_document_id", "user_id") VALUES (OLD."date_created", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."recap_document_id", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_2ec38 ON "favorites_prayer";
            CREATE  TRIGGER pgtrigger_custom_snapshot_update_2ec38
                AFTER UPDATE ON "favorites_prayer"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."recap_document_id" IS DISTINCT FROM NEW."recap_document_id")
                EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2ec38();

            COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2ec38 ON "favorites_prayer" IS '1526ae403d2c34a5827cd3b5008b89e7a560f831';
        ;
--
-- Create trigger custom_snapshot_update on model usertag
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

            CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_ee5b4()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified", "description", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "published", "title", "user_id") VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."published", OLD."title", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_ee5b4 ON "favorites_usertag";
            CREATE  TRIGGER pgtrigger_custom_snapshot_update_ee5b4
                AFTER UPDATE ON "favorites_usertag"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."name" IS DISTINCT FROM NEW."name" OR OLD."title" IS DISTINCT FROM NEW."title" OR OLD."description" IS DISTINCT FROM NEW."description" OR OLD."published" IS DISTINCT FROM NEW."published")
                EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_ee5b4();

            COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_ee5b4 ON "favorites_usertag" IS '1ffbd033a649407382f27b0b23bdaaffba58140a';
        ;
COMMIT;
