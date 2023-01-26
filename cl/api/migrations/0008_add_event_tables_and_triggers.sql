BEGIN;
--
-- Create model WebhookHistoryEvent
--
CREATE TABLE "api_webhookhistoryevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "event_type"     integer                  NOT NULL,
    "url"            varchar(2000)            NOT NULL,
    "enabled"        boolean                  NOT NULL,
    "version"        integer                  NOT NULL,
    "failure_count"  integer                  NOT NULL
);
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
    INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled",
                                           "event_type", "failure_count", "id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id", "url", "user_id",
                                           "version")
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

COMMENT ON TRIGGER pgtrigger_snapshot_insert_81718 ON "api_webhook" IS 'd6d8359832eed68e0e3aa21cd83aa53fb32d1ff9';
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
    INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled",
                                           "event_type", "failure_count", "id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id", "url", "user_id",
                                           "version")
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

COMMENT ON TRIGGER pgtrigger_snapshot_update_980eb ON "api_webhook" IS 'e8013d2a078cc8311e3fb1c81e247c09db921251';
;
--
-- Add field pgh_context to webhookhistoryevent
--
ALTER TABLE "api_webhookhistoryevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to webhookhistoryevent
--
ALTER TABLE "api_webhookhistoryevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to webhookhistoryevent
--
ALTER TABLE "api_webhookhistoryevent"
    ADD COLUMN "user_id" integer NOT NULL;
CREATE INDEX "api_webhookhistoryevent_pgh_context_id_cc48bf3f" ON "api_webhookhistoryevent" ("pgh_context_id");
CREATE INDEX "api_webhookhistoryevent_pgh_obj_id_1175efd1" ON "api_webhookhistoryevent" ("pgh_obj_id");
CREATE INDEX "api_webhookhistoryevent_user_id_ef198c77" ON "api_webhookhistoryevent" ("user_id");
COMMIT;
