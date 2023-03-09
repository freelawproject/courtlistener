BEGIN;
--
-- Create model AlertEvent
--
CREATE TABLE "alerts_alertevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "date_last_hit"  timestamp with time zone NULL,
    "name"           varchar(75)              NOT NULL,
    "query"          varchar(2500)            NOT NULL,
    "rate"           varchar(10)              NOT NULL,
    "secret_key"     varchar(40)              NOT NULL
);
--
-- Create model DocketAlertEvent
--
CREATE TABLE "alerts_docketalertevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "date_last_hit"  timestamp with time zone NULL,
    "secret_key"     varchar(40)              NOT NULL,
    "alert_type"     smallint                 NOT NULL
);
--
-- Create trigger snapshot_insert on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_cff3d()
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
    INSERT INTO "alerts_alertevent" ("date_created", "date_last_hit", "date_modified",
                                     "id", "name", "pgh_context_id", "pgh_created_at",
                                     "pgh_label", "pgh_obj_id", "query", "rate",
                                     "secret_key", "user_id")
    VALUES (NEW."date_created", NEW."date_last_hit", NEW."date_modified", NEW."id",
            NEW."name", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."query",
            NEW."rate", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cff3d ON "alerts_alert";
CREATE TRIGGER pgtrigger_snapshot_insert_cff3d
    AFTER INSERT
    ON "alerts_alert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_cff3d();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_cff3d ON "alerts_alert" IS '907312d0810a79ed5bd1affecfd8bbbab449a03a';
;
--
-- Create trigger snapshot_update on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_691d5()
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
    INSERT INTO "alerts_alertevent" ("date_created", "date_last_hit", "date_modified",
                                     "id", "name", "pgh_context_id", "pgh_created_at",
                                     "pgh_label", "pgh_obj_id", "query", "rate",
                                     "secret_key", "user_id")
    VALUES (NEW."date_created", NEW."date_last_hit", NEW."date_modified", NEW."id",
            NEW."name", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."query",
            NEW."rate", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_691d5 ON "alerts_alert";
CREATE TRIGGER pgtrigger_snapshot_update_691d5
    AFTER UPDATE
    ON "alerts_alert"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_691d5();

COMMENT ON TRIGGER pgtrigger_snapshot_update_691d5 ON "alerts_alert" IS 'f7e2b2f927a09fa01ed53ade96cab4e71a821734';
;
--
-- Create trigger snapshot_insert on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_f3fdd()
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
    INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created",
                                           "date_last_hit", "date_modified",
                                           "docket_id", "id", "pgh_context_id",
                                           "pgh_created_at", "pgh_label", "pgh_obj_id",
                                           "secret_key", "user_id")
    VALUES (NEW."alert_type", NEW."date_created", NEW."date_last_hit",
            NEW."date_modified", NEW."docket_id", NEW."id", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_f3fdd ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_snapshot_insert_f3fdd
    AFTER INSERT
    ON "alerts_docketalert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_f3fdd();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_f3fdd ON "alerts_docketalert" IS 'eede0c0fc7c8775ba94bb0a6d9920b9e2b540103';
;
--
-- Create trigger snapshot_update on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_2c804()
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
    INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created",
                                           "date_last_hit", "date_modified",
                                           "docket_id", "id", "pgh_context_id",
                                           "pgh_created_at", "pgh_label", "pgh_obj_id",
                                           "secret_key", "user_id")
    VALUES (NEW."alert_type", NEW."date_created", NEW."date_last_hit",
            NEW."date_modified", NEW."docket_id", NEW."id", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2c804 ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_snapshot_update_2c804
    AFTER UPDATE
    ON "alerts_docketalert"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_2c804();

COMMENT ON TRIGGER pgtrigger_snapshot_update_2c804 ON "alerts_docketalert" IS '03cc481405ab3524896a2816845b09ccfb0ba95f';
;
--
-- Add field docket to docketalertevent
--
ALTER TABLE "alerts_docketalertevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to docketalertevent
--
ALTER TABLE "alerts_docketalertevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to docketalertevent
--
ALTER TABLE "alerts_docketalertevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to docketalertevent
--
ALTER TABLE "alerts_docketalertevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field pgh_context to alertevent
--
ALTER TABLE "alerts_alertevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to alertevent
--
ALTER TABLE "alerts_alertevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to alertevent
--
ALTER TABLE "alerts_alertevent"
    ADD COLUMN "user_id" integer NOT NULL;
CREATE INDEX "alerts_docketalertevent_docket_id_4ec0a932" ON "alerts_docketalertevent" ("docket_id");
CREATE INDEX "alerts_docketalertevent_pgh_context_id_04eaa765" ON "alerts_docketalertevent" ("pgh_context_id");
CREATE INDEX "alerts_docketalertevent_pgh_obj_id_72e175df" ON "alerts_docketalertevent" ("pgh_obj_id");
CREATE INDEX "alerts_docketalertevent_user_id_c159a718" ON "alerts_docketalertevent" ("user_id");
CREATE INDEX "alerts_alertevent_pgh_context_id_78189dff" ON "alerts_alertevent" ("pgh_context_id");
CREATE INDEX "alerts_alertevent_pgh_obj_id_5f2e5901" ON "alerts_alertevent" ("pgh_obj_id");
CREATE INDEX "alerts_alertevent_user_id_24fb9e7e" ON "alerts_alertevent" ("user_id");
COMMIT;
