BEGIN;
--
-- Create model DonationEvent
--
CREATE TABLE "donate_donationevent"
(
    "pgh_id"               serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"       timestamp with time zone NOT NULL,
    "pgh_label"            text                     NOT NULL,
    "id"                   integer                  NOT NULL,
    "date_created"         timestamp with time zone NOT NULL,
    "date_modified"        timestamp with time zone NOT NULL,
    "clearing_date"        timestamp with time zone NULL,
    "send_annual_reminder" boolean                  NOT NULL,
    "amount"               numeric(10, 2)           NOT NULL,
    "payment_provider"     varchar(50)              NOT NULL,
    "payment_id"           varchar(64)              NOT NULL,
    "transaction_id"       varchar(64)              NULL,
    "status"               smallint                 NOT NULL,
    "referrer"             text                     NOT NULL
);
--
-- Create model MonthlyDonationEvent
--
CREATE TABLE "donate_monthlydonationevent"
(
    "pgh_id"                  serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"          timestamp with time zone NOT NULL,
    "pgh_label"               text                     NOT NULL,
    "id"                      integer                  NOT NULL,
    "date_created"            timestamp with time zone NOT NULL,
    "date_modified"           timestamp with time zone NOT NULL,
    "enabled"                 boolean                  NOT NULL,
    "payment_provider"        varchar(50)              NOT NULL,
    "monthly_donation_amount" numeric(10, 2)           NOT NULL,
    "monthly_donation_day"    smallint                 NOT NULL,
    "stripe_customer_id"      varchar(200)             NOT NULL,
    "failure_count"           smallint                 NOT NULL
);
--
-- Create trigger snapshot_insert on model donation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_e1095()
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
    INSERT INTO "donate_donationevent" ("amount", "clearing_date", "date_created",
                                        "date_modified", "donor_id", "id", "payment_id",
                                        "payment_provider", "pgh_context_id",
                                        "pgh_created_at", "pgh_label", "pgh_obj_id",
                                        "referrer", "send_annual_reminder", "status",
                                        "transaction_id")
    VALUES (NEW."amount", NEW."clearing_date", NEW."date_created", NEW."date_modified",
            NEW."donor_id", NEW."id", NEW."payment_id", NEW."payment_provider",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."referrer",
            NEW."send_annual_reminder", NEW."status", NEW."transaction_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_e1095 ON "donate_donation";
CREATE TRIGGER pgtrigger_snapshot_insert_e1095
    AFTER INSERT
    ON "donate_donation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_e1095();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_e1095 ON "donate_donation" IS '5f7aab9346564255e3c6c22dab89fdc5a8d2eeef';
;
--
-- Create trigger snapshot_update on model donation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cc68b()
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
    INSERT INTO "donate_donationevent" ("amount", "clearing_date", "date_created",
                                        "date_modified", "donor_id", "id", "payment_id",
                                        "payment_provider", "pgh_context_id",
                                        "pgh_created_at", "pgh_label", "pgh_obj_id",
                                        "referrer", "send_annual_reminder", "status",
                                        "transaction_id")
    VALUES (NEW."amount", NEW."clearing_date", NEW."date_created", NEW."date_modified",
            NEW."donor_id", NEW."id", NEW."payment_id", NEW."payment_provider",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."referrer",
            NEW."send_annual_reminder", NEW."status", NEW."transaction_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc68b ON "donate_donation";
CREATE TRIGGER pgtrigger_snapshot_update_cc68b
    AFTER UPDATE
    ON "donate_donation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cc68b();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cc68b ON "donate_donation" IS 'd4b84b83bc281dd0a772fa488c83e615d9783d0f';
;
--
-- Create trigger snapshot_insert on model monthlydonation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_6a386()
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
    INSERT INTO "donate_monthlydonationevent" ("date_created", "date_modified",
                                               "donor_id", "enabled", "failure_count",
                                               "id", "monthly_donation_amount",
                                               "monthly_donation_day",
                                               "payment_provider", "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "stripe_customer_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."donor_id", NEW."enabled",
            NEW."failure_count", NEW."id", NEW."monthly_donation_amount",
            NEW."monthly_donation_day", NEW."payment_provider", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."stripe_customer_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6a386 ON "donate_monthlydonation";
CREATE TRIGGER pgtrigger_snapshot_insert_6a386
    AFTER INSERT
    ON "donate_monthlydonation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_6a386();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_6a386 ON "donate_monthlydonation" IS 'c027cc38bd102ebda5ccf9c3987567d0a1ac4b74';
;
--
-- Create trigger snapshot_update on model monthlydonation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_87937()
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
    INSERT INTO "donate_monthlydonationevent" ("date_created", "date_modified",
                                               "donor_id", "enabled", "failure_count",
                                               "id", "monthly_donation_amount",
                                               "monthly_donation_day",
                                               "payment_provider", "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "stripe_customer_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."donor_id", NEW."enabled",
            NEW."failure_count", NEW."id", NEW."monthly_donation_amount",
            NEW."monthly_donation_day", NEW."payment_provider", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."stripe_customer_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_87937 ON "donate_monthlydonation";
CREATE TRIGGER pgtrigger_snapshot_update_87937
    AFTER UPDATE
    ON "donate_monthlydonation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_87937();

COMMENT ON TRIGGER pgtrigger_snapshot_update_87937 ON "donate_monthlydonation" IS 'fad24c80aa472c771c3a5d643dd73003bf3e6611';
;
--
-- Add field donor to monthlydonationevent
--
ALTER TABLE "donate_monthlydonationevent"
    ADD COLUMN "donor_id" integer NULL;
--
-- Add field pgh_context to monthlydonationevent
--
ALTER TABLE "donate_monthlydonationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to monthlydonationevent
--
ALTER TABLE "donate_monthlydonationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field donor to donationevent
--
ALTER TABLE "donate_donationevent"
    ADD COLUMN "donor_id" integer NULL;
--
-- Add field pgh_context to donationevent
--
ALTER TABLE "donate_donationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to donationevent
--
ALTER TABLE "donate_donationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
CREATE INDEX "donate_monthlydonationevent_donor_id_2f72d742" ON "donate_monthlydonationevent" ("donor_id");
CREATE INDEX "donate_monthlydonationevent_pgh_context_id_d8834484" ON "donate_monthlydonationevent" ("pgh_context_id");
CREATE INDEX "donate_monthlydonationevent_pgh_obj_id_5ffbfc06" ON "donate_monthlydonationevent" ("pgh_obj_id");
CREATE INDEX "donate_donationevent_donor_id_48483164" ON "donate_donationevent" ("donor_id");
CREATE INDEX "donate_donationevent_pgh_context_id_8c1c86c1" ON "donate_donationevent" ("pgh_context_id");
CREATE INDEX "donate_donationevent_pgh_obj_id_8aaac66f" ON "donate_donationevent" ("pgh_obj_id");
COMMIT;
