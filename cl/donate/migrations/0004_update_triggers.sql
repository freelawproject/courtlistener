BEGIN;
--
-- Remove trigger snapshot_insert from model donation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_e1095 ON "donate_donation";
--
-- Remove trigger snapshot_update from model donation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc68b ON "donate_donation";
--
-- Remove trigger snapshot_insert from model monthlydonation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6a386 ON "donate_monthlydonation";
--
-- Remove trigger snapshot_update from model monthlydonation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_87937 ON "donate_monthlydonation";
--
-- Create trigger custom_snapshot_insert on model donation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_4449d()
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
    INSERT INTO "donate_donationevent" ("amount", "clearing_date", "date_created", "date_modified", "donor_id", "id",
                                        "payment_id", "payment_provider", "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "referrer", "send_annual_reminder", "status",
                                        "transaction_id")
    VALUES (NEW."amount", NEW."clearing_date", NEW."date_created", NEW."date_modified", NEW."donor_id", NEW."id",
            NEW."payment_id", NEW."payment_provider", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."referrer", NEW."send_annual_reminder", NEW."status", NEW."transaction_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_4449d ON "donate_donation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_4449d
    AFTER INSERT
    ON "donate_donation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_4449d();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_4449d ON "donate_donation" IS '664496d2d546bc6786bca92e0f769e0ca57b7330';
;
--
-- Create trigger custom_snapshot_update on model donation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_5933b()
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
    INSERT INTO "donate_donationevent" ("amount", "clearing_date", "date_created", "date_modified", "donor_id", "id",
                                        "payment_id", "payment_provider", "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "referrer", "send_annual_reminder", "status",
                                        "transaction_id")
    VALUES (OLD."amount", OLD."clearing_date", OLD."date_created", OLD."date_modified", OLD."donor_id", OLD."id",
            OLD."payment_id", OLD."payment_provider", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."referrer", OLD."send_annual_reminder", OLD."status", OLD."transaction_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_5933b ON "donate_donation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_5933b
    AFTER UPDATE
    ON "donate_donation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_5933b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_5933b ON "donate_donation" IS 'ccf128f8ca2b7fa8188cf0afce15f91f022c1a37';
;
--
-- Create trigger custom_snapshot_insert on model monthlydonation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_60280()
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
    INSERT INTO "donate_monthlydonationevent" ("date_created", "date_modified", "donor_id", "enabled", "failure_count",
                                               "id", "monthly_donation_amount", "monthly_donation_day",
                                               "payment_provider", "pgh_context_id", "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "stripe_customer_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."donor_id", NEW."enabled", NEW."failure_count", NEW."id",
            NEW."monthly_donation_amount", NEW."monthly_donation_day", NEW."payment_provider", _pgh_attach_context(),
            NOW(), 'custom_snapshot', NEW."id", NEW."stripe_customer_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_60280 ON "donate_monthlydonation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_60280
    AFTER INSERT
    ON "donate_monthlydonation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_60280();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_60280 ON "donate_monthlydonation" IS '16616daaa4fe294d4a20b78dda3d9ceb285e2948';
;
--
-- Create trigger custom_snapshot_update on model monthlydonation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_997e1()
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
    INSERT INTO "donate_monthlydonationevent" ("date_created", "date_modified", "donor_id", "enabled", "failure_count",
                                               "id", "monthly_donation_amount", "monthly_donation_day",
                                               "payment_provider", "pgh_context_id", "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "stripe_customer_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."donor_id", OLD."enabled", OLD."failure_count", OLD."id",
            OLD."monthly_donation_amount", OLD."monthly_donation_day", OLD."payment_provider", _pgh_attach_context(),
            NOW(), 'custom_snapshot', OLD."id", OLD."stripe_customer_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_997e1 ON "donate_monthlydonation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_997e1
    AFTER UPDATE
    ON "donate_monthlydonation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_997e1();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_997e1 ON "donate_monthlydonation" IS '8e5f76fd507b4af5a13a0fe2896c05646a9e3569';
;
COMMIT;
