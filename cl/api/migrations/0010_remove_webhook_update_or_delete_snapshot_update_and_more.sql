BEGIN;
--
-- Remove trigger update_or_delete_snapshot_update from model webhook
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_224f9 ON "api_webhook";
--
-- Create trigger update_or_delete_snapshot_update on model webhook
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_224f9()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled", "event_type", "failure_count", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url", "user_id", "version") VALUES (OLD."date_created", OLD."date_modified", OLD."enabled", OLD."event_type", OLD."failure_count", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."url", OLD."user_id", OLD."version"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_224f9 ON "api_webhook";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_224f9
                AFTER UPDATE ON "api_webhook"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."event_type" IS DISTINCT FROM (NEW."event_type") OR OLD."url" IS DISTINCT FROM (NEW."url") OR OLD."enabled" IS DISTINCT FROM (NEW."enabled") OR OLD."version" IS DISTINCT FROM (NEW."version") OR OLD."failure_count" IS DISTINCT FROM (NEW."failure_count"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_224f9();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_224f9 ON "api_webhook" IS '9e47d58e531c3ece232c48322579e379f2852547';
        
COMMIT;
