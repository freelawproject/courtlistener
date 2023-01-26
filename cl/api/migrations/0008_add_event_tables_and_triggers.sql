BEGIN;
--
-- Create trigger snapshot_insert on model webhook
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_81718()
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
    INSERT INTO "api_webhookevent" ("date_created", "date_modified", "enabled",
                                    "event_type", "failure_count", "id",
                                    "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "url", "user_id", "version")
    VALUES (NEW."date_created", NEW."date_modified", NEW."enabled", NEW."event_type",
            NEW."failure_count", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."url", NEW."user_id", NEW."version");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_81718 ON "api_webhook";
CREATE TRIGGER pgtrigger_snapshot_insert_81718
    AFTER INSERT
    ON "api_webhook"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_81718();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_81718 ON "api_webhook" IS 'a2420e8215cc7e2ed382545cb396ce141e00c1db';
;
--
-- Create trigger snapshot_update on model webhook
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_980eb()
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
    INSERT INTO "api_webhookevent" ("date_created", "date_modified", "enabled",
                                    "event_type", "failure_count", "id",
                                    "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "url", "user_id", "version")
    VALUES (NEW."date_created", NEW."date_modified", NEW."enabled", NEW."event_type",
            NEW."failure_count", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."url", NEW."user_id", NEW."version");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_980eb ON "api_webhook";
CREATE TRIGGER pgtrigger_snapshot_update_980eb
    AFTER UPDATE
    ON "api_webhook"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_980eb();

COMMENT ON TRIGGER pgtrigger_snapshot_update_980eb ON "api_webhook" IS '7e7e23e049b7f1a61d745a0efd9175d140a5f6cc';
;
COMMIT;
