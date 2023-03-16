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
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."donor_id" IS DISTINCT FROM NEW."donor_id" OR OLD."clearing_date" IS DISTINCT FROM NEW."clearing_date" OR
          OLD."send_annual_reminder" IS DISTINCT FROM NEW."send_annual_reminder" OR
          OLD."amount" IS DISTINCT FROM NEW."amount" OR
          OLD."payment_provider" IS DISTINCT FROM NEW."payment_provider" OR
          OLD."payment_id" IS DISTINCT FROM NEW."payment_id" OR
          OLD."transaction_id" IS DISTINCT FROM NEW."transaction_id" OR OLD."status" IS DISTINCT FROM NEW."status" OR
          OLD."referrer" IS DISTINCT FROM NEW."referrer")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_5933b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_5933b ON "donate_donation" IS 'ed3acd2b086da50664453a3f6a76277fb3c1edea';
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
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."donor_id" IS DISTINCT FROM NEW."donor_id" OR OLD."enabled" IS DISTINCT FROM NEW."enabled" OR
          OLD."payment_provider" IS DISTINCT FROM NEW."payment_provider" OR
          OLD."monthly_donation_amount" IS DISTINCT FROM NEW."monthly_donation_amount" OR
          OLD."monthly_donation_day" IS DISTINCT FROM NEW."monthly_donation_day" OR
          OLD."stripe_customer_id" IS DISTINCT FROM NEW."stripe_customer_id" OR
          OLD."failure_count" IS DISTINCT FROM NEW."failure_count")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_997e1();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_997e1 ON "donate_monthlydonation" IS '28ecf8a37098eb8a099120c15d09e894b9a9b853';
;
COMMIT;
