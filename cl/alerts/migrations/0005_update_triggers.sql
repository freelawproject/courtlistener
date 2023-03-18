BEGIN;
--
-- Remove trigger snapshot_insert from model alert
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cff3d ON "alerts_alert";
--
-- Remove trigger snapshot_update from model alert
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_691d5 ON "alerts_alert";
--
-- Remove trigger snapshot_insert from model docketalert
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_f3fdd ON "alerts_docketalert";
--
-- Remove trigger snapshot_update from model docketalert
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2c804 ON "alerts_docketalert";
--
-- Create trigger update_or_delete_snapshot_update on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_1285f()
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
    INSERT INTO "alerts_alertevent" ("date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id",
                                     "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key",
                                     "user_id")
    VALUES (OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_1285f ON "alerts_alert";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_1285f
    AFTER UPDATE
    ON "alerts_alert"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."date_last_hit" IS DISTINCT FROM NEW."date_last_hit" OR
          OLD."name" IS DISTINCT FROM NEW."name" OR OLD."query" IS DISTINCT FROM NEW."query" OR
          OLD."rate" IS DISTINCT FROM NEW."rate" OR OLD."secret_key" IS DISTINCT FROM NEW."secret_key")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_1285f();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_1285f ON "alerts_alert" IS '8112f80be041b38ac3d0a125f301204fd6423cd3';
;
--
-- Create trigger update_or_delete_snapshot_delete on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_96037()
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
    INSERT INTO "alerts_alertevent" ("date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id",
                                     "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key",
                                     "user_id")
    VALUES (OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_96037 ON "alerts_alert";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_96037
    AFTER DELETE
    ON "alerts_alert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_96037();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_96037 ON "alerts_alert" IS '27189303378fea40e58a12b53035f75d81e76632';
;
--
-- Create trigger update_or_delete_snapshot_update on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_c2b33()
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
    INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "docket_id",
                                           "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                           "secret_key", "user_id")
    VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."docket_id", OLD."id",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_c2b33 ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_c2b33
    AFTER UPDATE
    ON "alerts_docketalert"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."date_last_hit" IS DISTINCT FROM NEW."date_last_hit" OR
          OLD."docket_id" IS DISTINCT FROM NEW."docket_id" OR OLD."user_id" IS DISTINCT FROM NEW."user_id" OR
          OLD."secret_key" IS DISTINCT FROM NEW."secret_key" OR OLD."alert_type" IS DISTINCT FROM NEW."alert_type")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_c2b33();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_c2b33 ON "alerts_docketalert" IS '89b88f2e0a243e9cb89c8890bd2bb1a2687953df';
;
--
-- Create trigger update_or_delete_snapshot_delete on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_641ee()
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
    INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "docket_id",
                                           "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                           "secret_key", "user_id")
    VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."docket_id", OLD."id",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_641ee ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_641ee
    AFTER DELETE
    ON "alerts_docketalert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_641ee();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_641ee ON "alerts_docketalert" IS 'afac64cc4b14c1ef7069751813659220f7085861';
;
COMMIT;
