BEGIN;
--
-- Remove trigger update_or_delete_snapshot_delete from model alert
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_96037 ON "alerts_alert";
--
-- Remove trigger update_or_delete_snapshot_update from model alert
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_1285f ON "alerts_alert";
--
-- Add field alert_type to alert
--
ALTER TABLE "alerts_alert" ADD COLUMN "alert_type" varchar(3) DEFAULT 'o' NOT NULL;
ALTER TABLE "alerts_alert" ALTER COLUMN "alert_type" DROP DEFAULT;
--
-- Add field alert_type to alertevent
--
ALTER TABLE "alerts_alertevent" ADD COLUMN "alert_type" varchar(3) DEFAULT 'o' NOT NULL;
ALTER TABLE "alerts_alertevent" ALTER COLUMN "alert_type" DROP DEFAULT;
--
-- Create trigger update_or_delete_snapshot_update on model alert
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_1285f()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "alerts_alertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_1285f ON "alerts_alert";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_1285f
                AFTER UPDATE ON "alerts_alert"


                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."date_last_hit" IS DISTINCT FROM (NEW."date_last_hit") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."query" IS DISTINCT FROM (NEW."query") OR OLD."rate" IS DISTINCT FROM (NEW."rate") OR OLD."alert_type" IS DISTINCT FROM (NEW."alert_type") OR OLD."secret_key" IS DISTINCT FROM (NEW."secret_key"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_1285f();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_1285f ON "alerts_alert" IS '42b4804e1bd56a147658e07f14ee253e226ba809';

--
-- Create trigger update_or_delete_snapshot_delete on model alert
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_96037()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "alerts_alertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_96037 ON "alerts_alert";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_delete_96037
                AFTER DELETE ON "alerts_alert"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_96037();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_96037 ON "alerts_alert" IS 'e964b655ff3f1c4613682420332696dba8e2f620';

COMMIT;
