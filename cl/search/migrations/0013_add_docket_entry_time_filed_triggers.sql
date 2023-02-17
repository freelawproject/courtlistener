BEGIN;
--
-- Remove trigger snapshot_insert from model docketentry
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_2de73 ON "search_docketentry";
--
-- Remove trigger snapshot_update from model docketentry
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d8176 ON "search_docketentry";
--
-- Add field time_filed to docketentryevent
--
ALTER TABLE "search_docketentryevent" ADD COLUMN "time_filed" time NULL;
--
-- Alter field date_filed on docketentry
--
--
-- Alter field date_filed on docketentryevent
--
--
-- Create trigger snapshot_insert on model docketentry
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_2de73()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketentryevent" ("date_created", "date_filed", "date_modified", "description", "docket_id", "entry_number", "id", "pacer_sequence_number", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_sequence_number", "time_filed") VALUES (NEW."date_created", NEW."date_filed", NEW."date_modified", NEW."description", NEW."docket_id", NEW."entry_number", NEW."id", NEW."pacer_sequence_number", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."recap_sequence_number", NEW."time_filed"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_2de73 ON "search_docketentry";
            CREATE  TRIGGER pgtrigger_snapshot_insert_2de73
                AFTER INSERT ON "search_docketentry"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_2de73();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_2de73 ON "search_docketentry" IS '5bdf83ede5ee24b635a78f3d61b8a9a37a09782d';
        ;
--
-- Create trigger snapshot_update on model docketentry
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_d8176()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketentryevent" ("date_created", "date_filed", "date_modified", "description", "docket_id", "entry_number", "id", "pacer_sequence_number", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_sequence_number", "time_filed") VALUES (NEW."date_created", NEW."date_filed", NEW."date_modified", NEW."description", NEW."docket_id", NEW."entry_number", NEW."id", NEW."pacer_sequence_number", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."recap_sequence_number", NEW."time_filed"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d8176 ON "search_docketentry";
            CREATE  TRIGGER pgtrigger_snapshot_update_d8176
                AFTER UPDATE ON "search_docketentry"


                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_d8176();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_d8176 ON "search_docketentry" IS 'd34e74de0dd87398f26bdb49ed27c7c60c2756de';
        ;
COMMIT;
