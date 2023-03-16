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
-- Create trigger custom_snapshot_insert on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_12a4b()
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
    VALUES (NEW."date_created", NEW."date_last_hit", NEW."date_modified", NEW."id", NEW."name", _pgh_attach_context(),
            NOW(), 'custom_snapshot', NEW."id", NEW."query", NEW."rate", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_12a4b ON "alerts_alert";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_12a4b
    AFTER INSERT
    ON "alerts_alert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_12a4b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_12a4b ON "alerts_alert" IS '1c953596cd9e5485227c23c06e19cce920b52eae';
;
--
-- Create trigger custom_snapshot_update on model alert
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_f51a7()
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
            NOW(), 'custom_snapshot', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_f51a7 ON "alerts_alert";
CREATE TRIGGER pgtrigger_custom_snapshot_update_f51a7
    AFTER UPDATE
    ON "alerts_alert"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_f51a7();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_f51a7 ON "alerts_alert" IS 'fdb811e543ae7a708472e67ec5924bff7c872954';
;
--
-- Create trigger custom_snapshot_insert on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_beef4()
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
    VALUES (NEW."alert_type", NEW."date_created", NEW."date_last_hit", NEW."date_modified", NEW."docket_id", NEW."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."secret_key", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_beef4 ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_beef4
    AFTER INSERT
    ON "alerts_docketalert"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_beef4();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_beef4 ON "alerts_docketalert" IS 'da4247073d6ac09d8a4c281d25fbff179daa1b33';
;
--
-- Create trigger custom_snapshot_update on model docketalert
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_3fcf1()
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
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."secret_key", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_3fcf1 ON "alerts_docketalert";
CREATE TRIGGER pgtrigger_custom_snapshot_update_3fcf1
    AFTER UPDATE
    ON "alerts_docketalert"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_3fcf1();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_3fcf1 ON "alerts_docketalert" IS '18a8b2f426be5b6cfd25eeb5b47df85bd6c47b70';
;
COMMIT;
