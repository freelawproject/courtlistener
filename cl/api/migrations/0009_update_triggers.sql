BEGIN;
--
-- Remove trigger snapshot_insert from model webhook
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_81718 ON "api_webhook";
--
-- Remove trigger snapshot_update from model webhook
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_980eb ON "api_webhook";
--
-- Create trigger custom_snapshot_insert on model webhook
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_c3f55()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled", "event_type", "failure_count",
                                           "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url",
                                           "user_id", "version")
    VALUES (NEW."date_created", NEW."date_modified", NEW."enabled", NEW."event_type", NEW."failure_count", NEW."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."url", NEW."user_id", NEW."version");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_c3f55 ON "api_webhook";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_c3f55
    AFTER INSERT
    ON "api_webhook"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_c3f55();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_c3f55 ON "api_webhook" IS 'd1c8c10c49ada99369ce8d2cca614bc0feab6426';
;
--
-- Create trigger custom_snapshot_update on model webhook
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_fcc01()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled", "event_type", "failure_count",
                                           "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url",
                                           "user_id", "version")
    VALUES (OLD."date_created", OLD."date_modified", OLD."enabled", OLD."event_type", OLD."failure_count", OLD."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."url", OLD."user_id", OLD."version");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_fcc01 ON "api_webhook";
CREATE TRIGGER pgtrigger_custom_snapshot_update_fcc01
    AFTER UPDATE
    ON "api_webhook"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_fcc01();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_fcc01 ON "api_webhook" IS '6704a4d306024ba09a94c9168faeb046e5bbf0e7';
;
COMMIT;
