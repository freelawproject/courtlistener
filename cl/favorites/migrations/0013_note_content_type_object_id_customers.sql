BEGIN;
--
-- Remove trigger update_update from model note
--
DROP TRIGGER IF EXISTS pgtrigger_update_update_8ef2a ON "favorites_note";
--
-- Remove trigger delete_delete from model note
--
DROP TRIGGER IF EXISTS pgtrigger_delete_delete_eebc8 ON "favorites_note";
--
-- Add field content_type to note
--
ALTER TABLE "favorites_note" ADD COLUMN "content_type_id" integer NULL CONSTRAINT "favorites_note_content_type_id_a1aab4c0_fk_django_co" REFERENCES "django_content_type"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "favorites_note_content_type_id_a1aab4c0_fk_django_co" IMMEDIATE;
--
-- Add field object_id to note
--
ALTER TABLE "favorites_note" ADD COLUMN "object_id" integer NULL CHECK ("object_id" >= 0);
--
-- Create trigger update_update on model note
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_update_8ef2a()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "content_type_id", "date_created", "date_modified", "docket_id_id", "id", "name", "notes", "object_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_doc_id_id", "user_id") VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."content_type_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id", OLD."id", OLD."name", OLD."notes", OLD."object_id", _pgh_attach_context(), NOW(), 'update', OLD."id", OLD."recap_doc_id_id", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_update_8ef2a ON "favorites_note";
            CREATE  TRIGGER pgtrigger_update_update_8ef2a
                AFTER UPDATE ON "favorites_note"
                
                
                FOR EACH ROW WHEN (OLD."audio_id_id" IS DISTINCT FROM (NEW."audio_id_id") OR OLD."cluster_id_id" IS DISTINCT FROM (NEW."cluster_id_id") OR OLD."content_type_id" IS DISTINCT FROM (NEW."content_type_id") OR OLD."docket_id_id" IS DISTINCT FROM (NEW."docket_id_id") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."notes" IS DISTINCT FROM (NEW."notes") OR OLD."object_id" IS DISTINCT FROM (NEW."object_id") OR OLD."recap_doc_id_id" IS DISTINCT FROM (NEW."recap_doc_id_id") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id"))
                EXECUTE PROCEDURE pgtrigger_update_update_8ef2a();

            COMMENT ON TRIGGER pgtrigger_update_update_8ef2a ON "favorites_note" IS '632e7f6ec5887fbf2e3fa7a880f0e27596eb8f48';
        
--
-- Create trigger delete_delete on model note
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

            CREATE OR REPLACE FUNCTION pgtrigger_delete_delete_eebc8()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "content_type_id", "date_created", "date_modified", "docket_id_id", "id", "name", "notes", "object_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_doc_id_id", "user_id") VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."content_type_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id", OLD."id", OLD."name", OLD."notes", OLD."object_id", _pgh_attach_context(), NOW(), 'delete', OLD."id", OLD."recap_doc_id_id", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_delete_delete_eebc8 ON "favorites_note";
            CREATE  TRIGGER pgtrigger_delete_delete_eebc8
                AFTER DELETE ON "favorites_note"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_delete_delete_eebc8();

            COMMENT ON TRIGGER pgtrigger_delete_delete_eebc8 ON "favorites_note" IS '066d5f65b6ee4a48eef5ec26cbaf265e3123c448';
        
COMMIT;
