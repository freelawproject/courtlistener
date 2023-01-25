BEGIN;
--
-- Create model AgreementEvent
--
CREATE TABLE "disclosures_agreementevent"
(
    "pgh_id"            serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"    timestamp with time zone NOT NULL,
    "pgh_label"         text                     NOT NULL,
    "id"                integer                  NOT NULL,
    "date_created"      timestamp with time zone NOT NULL,
    "date_modified"     timestamp with time zone NOT NULL,
    "date_raw"          text                     NOT NULL,
    "parties_and_terms" text                     NOT NULL,
    "redacted"          boolean                  NOT NULL
);
--
-- Create model DebtEvent
--
CREATE TABLE "disclosures_debtevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "creditor_name"  text                     NOT NULL,
    "description"    text                     NOT NULL,
    "value_code"     varchar(5)               NOT NULL,
    "redacted"       boolean                  NOT NULL
);
--
-- Create model FinancialDisclosureEvent
--
CREATE TABLE "disclosures_financialdisclosureevent"
(
    "pgh_id"               serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"       timestamp with time zone NOT NULL,
    "pgh_label"            text                     NOT NULL,
    "id"                   integer                  NOT NULL,
    "date_created"         timestamp with time zone NOT NULL,
    "date_modified"        timestamp with time zone NOT NULL,
    "year"                 smallint                 NOT NULL,
    "download_filepath"    text                     NOT NULL,
    "filepath"             varchar(300)             NOT NULL,
    "thumbnail"            varchar(300)             NULL,
    "thumbnail_status"     smallint                 NOT NULL,
    "page_count"           smallint                 NOT NULL,
    "sha1"                 varchar(40)              NOT NULL,
    "report_type"          smallint                 NOT NULL,
    "is_amended"           boolean                  NULL,
    "addendum_content_raw" text                     NOT NULL,
    "addendum_redacted"    boolean                  NOT NULL,
    "has_been_extracted"   boolean                  NOT NULL
);
--
-- Create model GiftEvent
--
CREATE TABLE "disclosures_giftevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "source"         text                     NOT NULL,
    "description"    text                     NOT NULL,
    "value"          text                     NOT NULL,
    "redacted"       boolean                  NOT NULL
);
--
-- Create model InvestmentEvent
--
CREATE TABLE "disclosures_investmentevent"
(
    "pgh_id"                              serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"                      timestamp with time zone NOT NULL,
    "pgh_label"                           text                     NOT NULL,
    "id"                                  integer                  NOT NULL,
    "date_created"                        timestamp with time zone NOT NULL,
    "date_modified"                       timestamp with time zone NOT NULL,
    "page_number"                         integer                  NOT NULL,
    "description"                         text                     NOT NULL,
    "redacted"                            boolean                  NOT NULL,
    "income_during_reporting_period_code" varchar(5)               NOT NULL,
    "income_during_reporting_period_type" text                     NOT NULL,
    "gross_value_code"                    varchar(5)               NOT NULL,
    "gross_value_method"                  varchar(5)               NOT NULL,
    "transaction_during_reporting_period" text                     NOT NULL,
    "transaction_date_raw"                varchar(40)              NOT NULL,
    "transaction_date"                    date                     NULL,
    "transaction_value_code"              varchar(5)               NOT NULL,
    "transaction_gain_code"               varchar(5)               NOT NULL,
    "transaction_partner"                 text                     NOT NULL,
    "has_inferred_values"                 boolean                  NOT NULL
);
--
-- Create model NonInvestmentIncomeEvent
--
CREATE TABLE "disclosures_noninvestmentincomeevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "date_raw"       text                     NOT NULL,
    "source_type"    text                     NOT NULL,
    "income_amount"  text                     NOT NULL,
    "redacted"       boolean                  NOT NULL
);
--
-- Create model PositionEvent
--
CREATE TABLE "disclosures_positionevent"
(
    "pgh_id"            serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"    timestamp with time zone NOT NULL,
    "pgh_label"         text                     NOT NULL,
    "id"                integer                  NOT NULL,
    "date_created"      timestamp with time zone NOT NULL,
    "date_modified"     timestamp with time zone NOT NULL,
    "position"          text                     NOT NULL,
    "organization_name" text                     NOT NULL,
    "redacted"          boolean                  NOT NULL
);
--
-- Create model ReimbursementEvent
--
CREATE TABLE "disclosures_reimbursementevent"
(
    "pgh_id"                 serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"         timestamp with time zone NOT NULL,
    "pgh_label"              text                     NOT NULL,
    "id"                     integer                  NOT NULL,
    "date_created"           timestamp with time zone NOT NULL,
    "date_modified"          timestamp with time zone NOT NULL,
    "source"                 text                     NOT NULL,
    "date_raw"               text                     NOT NULL,
    "location"               text                     NOT NULL,
    "purpose"                text                     NOT NULL,
    "items_paid_or_provided" text                     NOT NULL,
    "redacted"               boolean                  NOT NULL
);
--
-- Create model SpouseIncomeEvent
--
CREATE TABLE "disclosures_spouseincomeevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "source_type"    text                     NOT NULL,
    "date_raw"       text                     NOT NULL,
    "redacted"       boolean                  NOT NULL
);
--
-- Create trigger snapshot_insert on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_69a8c()
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
    INSERT INTO "disclosures_agreementevent" ("date_created", "date_modified",
                                              "date_raw", "financial_disclosure_id",
                                              "id", "parties_and_terms",
                                              "pgh_context_id", "pgh_created_at",
                                              "pgh_label", "pgh_obj_id", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."parties_and_terms",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_69a8c ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_snapshot_insert_69a8c
    AFTER INSERT
    ON "disclosures_agreement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_69a8c();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_69a8c ON "disclosures_agreement" IS 'ddf2a5e6c6125219b2389db05ad2d8e3ad453ec6';
;
--
-- Create trigger snapshot_update on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_e00c2()
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
    INSERT INTO "disclosures_agreementevent" ("date_created", "date_modified",
                                              "date_raw", "financial_disclosure_id",
                                              "id", "parties_and_terms",
                                              "pgh_context_id", "pgh_created_at",
                                              "pgh_label", "pgh_obj_id", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."parties_and_terms",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_e00c2 ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_snapshot_update_e00c2
    AFTER UPDATE
    ON "disclosures_agreement"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_e00c2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_e00c2 ON "disclosures_agreement" IS 'eb5f1240d4920247a1ebbfea7a035de6ff58efb3';
;
--
-- Create trigger snapshot_insert on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_684e3()
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
    INSERT INTO "disclosures_debtevent" ("creditor_name", "date_created",
                                         "date_modified", "description",
                                         "financial_disclosure_id", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted",
                                         "value_code")
    VALUES (NEW."creditor_name", NEW."date_created", NEW."date_modified",
            NEW."description", NEW."financial_disclosure_id", NEW."id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_684e3 ON "disclosures_debt";
CREATE TRIGGER pgtrigger_snapshot_insert_684e3
    AFTER INSERT
    ON "disclosures_debt"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_684e3();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_684e3 ON "disclosures_debt" IS 'adaf2e25fefe38d2f4f037350e5771b6c416d5c8';
;
--
-- Create trigger snapshot_update on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_93edc()
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
    INSERT INTO "disclosures_debtevent" ("creditor_name", "date_created",
                                         "date_modified", "description",
                                         "financial_disclosure_id", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted",
                                         "value_code")
    VALUES (NEW."creditor_name", NEW."date_created", NEW."date_modified",
            NEW."description", NEW."financial_disclosure_id", NEW."id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_93edc ON "disclosures_debt";
CREATE TRIGGER pgtrigger_snapshot_update_93edc
    AFTER UPDATE
    ON "disclosures_debt"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_93edc();

COMMENT ON TRIGGER pgtrigger_snapshot_update_93edc ON "disclosures_debt" IS '520ba5cb808a97f1a772eb4d7ce416c8144dcb8b';
;
--
-- Create trigger snapshot_insert on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_64c14()
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
    INSERT INTO "disclosures_financialdisclosureevent" ("addendum_content_raw",
                                                        "addendum_redacted",
                                                        "date_created", "date_modified",
                                                        "download_filepath", "filepath",
                                                        "has_been_extracted", "id",
                                                        "is_amended", "page_count",
                                                        "person_id", "pgh_context_id",
                                                        "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "report_type",
                                                        "sha1", "thumbnail",
                                                        "thumbnail_status", "year")
    VALUES (NEW."addendum_content_raw", NEW."addendum_redacted", NEW."date_created",
            NEW."date_modified", NEW."download_filepath", NEW."filepath",
            NEW."has_been_extracted", NEW."id", NEW."is_amended", NEW."page_count",
            NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."report_type", NEW."sha1", NEW."thumbnail", NEW."thumbnail_status",
            NEW."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_64c14 ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_snapshot_insert_64c14
    AFTER INSERT
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_64c14();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_64c14 ON "disclosures_financialdisclosure" IS '48a0a4a007d40d5bb95743a3e427d755c8bdbf0e';
;
--
-- Create trigger snapshot_update on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_28e98()
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
    INSERT INTO "disclosures_financialdisclosureevent" ("addendum_content_raw",
                                                        "addendum_redacted",
                                                        "date_created", "date_modified",
                                                        "download_filepath", "filepath",
                                                        "has_been_extracted", "id",
                                                        "is_amended", "page_count",
                                                        "person_id", "pgh_context_id",
                                                        "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "report_type",
                                                        "sha1", "thumbnail",
                                                        "thumbnail_status", "year")
    VALUES (NEW."addendum_content_raw", NEW."addendum_redacted", NEW."date_created",
            NEW."date_modified", NEW."download_filepath", NEW."filepath",
            NEW."has_been_extracted", NEW."id", NEW."is_amended", NEW."page_count",
            NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."report_type", NEW."sha1", NEW."thumbnail", NEW."thumbnail_status",
            NEW."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_28e98 ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_snapshot_update_28e98
    AFTER UPDATE
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_28e98();

COMMENT ON TRIGGER pgtrigger_snapshot_update_28e98 ON "disclosures_financialdisclosure" IS '54800fa2be6036d203cabcd3a45e5b7a499d9a1c';
;
--
-- Create trigger snapshot_insert on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_94042()
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
    INSERT INTO "disclosures_giftevent" ("date_created", "date_modified", "description",
                                         "financial_disclosure_id", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted",
                                         "source", "value")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."financial_disclosure_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."redacted", NEW."source", NEW."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_94042 ON "disclosures_gift";
CREATE TRIGGER pgtrigger_snapshot_insert_94042
    AFTER INSERT
    ON "disclosures_gift"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_94042();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_94042 ON "disclosures_gift" IS '01c135267a287ecb0e83703fc700d5ec035f59b3';
;
--
-- Create trigger snapshot_update on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_9e72b()
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
    INSERT INTO "disclosures_giftevent" ("date_created", "date_modified", "description",
                                         "financial_disclosure_id", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted",
                                         "source", "value")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."financial_disclosure_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."redacted", NEW."source", NEW."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_9e72b ON "disclosures_gift";
CREATE TRIGGER pgtrigger_snapshot_update_9e72b
    AFTER UPDATE
    ON "disclosures_gift"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_9e72b();

COMMENT ON TRIGGER pgtrigger_snapshot_update_9e72b ON "disclosures_gift" IS '8e15df8ab1bee900b1182cf44ca67b0dc7362387';
;
--
-- Create trigger snapshot_insert on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_cde17()
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
    INSERT INTO "disclosures_investmentevent" ("date_created", "date_modified",
                                               "description", "financial_disclosure_id",
                                               "gross_value_code", "gross_value_method",
                                               "has_inferred_values", "id",
                                               "income_during_reporting_period_code",
                                               "income_during_reporting_period_type",
                                               "page_number", "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "redacted",
                                               "transaction_date",
                                               "transaction_date_raw",
                                               "transaction_during_reporting_period",
                                               "transaction_gain_code",
                                               "transaction_partner",
                                               "transaction_value_code")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."financial_disclosure_id", NEW."gross_value_code",
            NEW."gross_value_method", NEW."has_inferred_values", NEW."id",
            NEW."income_during_reporting_period_code",
            NEW."income_during_reporting_period_type", NEW."page_number",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."transaction_date", NEW."transaction_date_raw",
            NEW."transaction_during_reporting_period", NEW."transaction_gain_code",
            NEW."transaction_partner", NEW."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cde17 ON "disclosures_investment";
CREATE TRIGGER pgtrigger_snapshot_insert_cde17
    AFTER INSERT
    ON "disclosures_investment"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_cde17();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_cde17 ON "disclosures_investment" IS 'ed475fdcf8b28ce84acaf028536b19ba73bd506b';
;
--
-- Create trigger snapshot_update on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_f6320()
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
    INSERT INTO "disclosures_investmentevent" ("date_created", "date_modified",
                                               "description", "financial_disclosure_id",
                                               "gross_value_code", "gross_value_method",
                                               "has_inferred_values", "id",
                                               "income_during_reporting_period_code",
                                               "income_during_reporting_period_type",
                                               "page_number", "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "pgh_obj_id", "redacted",
                                               "transaction_date",
                                               "transaction_date_raw",
                                               "transaction_during_reporting_period",
                                               "transaction_gain_code",
                                               "transaction_partner",
                                               "transaction_value_code")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."financial_disclosure_id", NEW."gross_value_code",
            NEW."gross_value_method", NEW."has_inferred_values", NEW."id",
            NEW."income_during_reporting_period_code",
            NEW."income_during_reporting_period_type", NEW."page_number",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."transaction_date", NEW."transaction_date_raw",
            NEW."transaction_during_reporting_period", NEW."transaction_gain_code",
            NEW."transaction_partner", NEW."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_f6320 ON "disclosures_investment";
CREATE TRIGGER pgtrigger_snapshot_update_f6320
    AFTER UPDATE
    ON "disclosures_investment"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_f6320();

COMMENT ON TRIGGER pgtrigger_snapshot_update_f6320 ON "disclosures_investment" IS '0705491613e79218bc9d6922c3906f9c35c2d097';
;
--
-- Create trigger snapshot_insert on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_c76a9()
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
    INSERT INTO "disclosures_noninvestmentincomeevent" ("date_created", "date_modified",
                                                        "date_raw",
                                                        "financial_disclosure_id", "id",
                                                        "income_amount",
                                                        "pgh_context_id",
                                                        "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "redacted",
                                                        "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."income_amount",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c76a9 ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_snapshot_insert_c76a9
    AFTER INSERT
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_c76a9();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_c76a9 ON "disclosures_noninvestmentincome" IS '12c4c6be9c10c23a862f4976b4d607f74f4f011a';
;
--
-- Create trigger snapshot_update on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_4b46e()
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
    INSERT INTO "disclosures_noninvestmentincomeevent" ("date_created", "date_modified",
                                                        "date_raw",
                                                        "financial_disclosure_id", "id",
                                                        "income_amount",
                                                        "pgh_context_id",
                                                        "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "redacted",
                                                        "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."income_amount",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."redacted",
            NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_4b46e ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_snapshot_update_4b46e
    AFTER UPDATE
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_4b46e();

COMMENT ON TRIGGER pgtrigger_snapshot_update_4b46e ON "disclosures_noninvestmentincome" IS '3c56b051bf9c98195775f437224a297075f489bf';
;
--
-- Create trigger snapshot_insert on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_c33c6()
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
    INSERT INTO "disclosures_positionevent" ("date_created", "date_modified",
                                             "financial_disclosure_id", "id",
                                             "organization_name", "pgh_context_id",
                                             "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "position", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."financial_disclosure_id",
            NEW."id", NEW."organization_name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."position", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c33c6 ON "disclosures_position";
CREATE TRIGGER pgtrigger_snapshot_insert_c33c6
    AFTER INSERT
    ON "disclosures_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_c33c6();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_c33c6 ON "disclosures_position" IS 'bb3e5fc3baf9fc7b2c3951bb5aaddd1820c877e4';
;
--
-- Create trigger snapshot_update on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6dbf5()
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
    INSERT INTO "disclosures_positionevent" ("date_created", "date_modified",
                                             "financial_disclosure_id", "id",
                                             "organization_name", "pgh_context_id",
                                             "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "position", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."financial_disclosure_id",
            NEW."id", NEW."organization_name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."position", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6dbf5 ON "disclosures_position";
CREATE TRIGGER pgtrigger_snapshot_update_6dbf5
    AFTER UPDATE
    ON "disclosures_position"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_6dbf5();

COMMENT ON TRIGGER pgtrigger_snapshot_update_6dbf5 ON "disclosures_position" IS '68dbea842e77f8e8b9cc3523824cbb0d83edc3f9';
;
--
-- Create trigger snapshot_insert on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_c2f93()
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
    INSERT INTO "disclosures_reimbursementevent" ("date_created", "date_modified",
                                                  "date_raw", "financial_disclosure_id",
                                                  "id", "items_paid_or_provided",
                                                  "location", "pgh_context_id",
                                                  "pgh_created_at", "pgh_label",
                                                  "pgh_obj_id", "purpose", "redacted",
                                                  "source")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."items_paid_or_provided",
            NEW."location", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."purpose", NEW."redacted", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c2f93 ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_snapshot_insert_c2f93
    AFTER INSERT
    ON "disclosures_reimbursement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_c2f93();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_c2f93 ON "disclosures_reimbursement" IS 'a63b0a100c9a76059df161b5c0b16c8da5250c84';
;
--
-- Create trigger snapshot_update on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_53701()
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
    INSERT INTO "disclosures_reimbursementevent" ("date_created", "date_modified",
                                                  "date_raw", "financial_disclosure_id",
                                                  "id", "items_paid_or_provided",
                                                  "location", "pgh_context_id",
                                                  "pgh_created_at", "pgh_label",
                                                  "pgh_obj_id", "purpose", "redacted",
                                                  "source")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", NEW."items_paid_or_provided",
            NEW."location", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."purpose", NEW."redacted", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_53701 ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_snapshot_update_53701
    AFTER UPDATE
    ON "disclosures_reimbursement"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_53701();

COMMENT ON TRIGGER pgtrigger_snapshot_update_53701 ON "disclosures_reimbursement" IS '2bf70ba3af70433d176910fb3a8c0b81af6e7727';
;
--
-- Create trigger snapshot_insert on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_5505f()
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
    INSERT INTO "disclosures_spouseincomeevent" ("date_created", "date_modified",
                                                 "date_raw", "financial_disclosure_id",
                                                 "id", "pgh_context_id",
                                                 "pgh_created_at", "pgh_label",
                                                 "pgh_obj_id", "redacted",
                                                 "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."redacted", NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_5505f ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_snapshot_insert_5505f
    AFTER INSERT
    ON "disclosures_spouseincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_5505f();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_5505f ON "disclosures_spouseincome" IS 'f1b6af11a3cc15accbff7bb323442c1266df2fa5';
;
--
-- Create trigger snapshot_update on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_37f1c()
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
    INSERT INTO "disclosures_spouseincomeevent" ("date_created", "date_modified",
                                                 "date_raw", "financial_disclosure_id",
                                                 "id", "pgh_context_id",
                                                 "pgh_created_at", "pgh_label",
                                                 "pgh_obj_id", "redacted",
                                                 "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw",
            NEW."financial_disclosure_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."redacted", NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_37f1c ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_snapshot_update_37f1c
    AFTER UPDATE
    ON "disclosures_spouseincome"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_37f1c();

COMMENT ON TRIGGER pgtrigger_snapshot_update_37f1c ON "disclosures_spouseincome" IS 'ac13e200ed063ed9d244db68631238ce71094821';
;
--
-- Add field financial_disclosure to spouseincomeevent
--
ALTER TABLE "disclosures_spouseincomeevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to spouseincomeevent
--
ALTER TABLE "disclosures_spouseincomeevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to spouseincomeevent
--
ALTER TABLE "disclosures_spouseincomeevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to reimbursementevent
--
ALTER TABLE "disclosures_reimbursementevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to reimbursementevent
--
ALTER TABLE "disclosures_reimbursementevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to reimbursementevent
--
ALTER TABLE "disclosures_reimbursementevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to positionevent
--
ALTER TABLE "disclosures_positionevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to positionevent
--
ALTER TABLE "disclosures_positionevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to positionevent
--
ALTER TABLE "disclosures_positionevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to noninvestmentincomeevent
--
ALTER TABLE "disclosures_noninvestmentincomeevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to noninvestmentincomeevent
--
ALTER TABLE "disclosures_noninvestmentincomeevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to noninvestmentincomeevent
--
ALTER TABLE "disclosures_noninvestmentincomeevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to investmentevent
--
ALTER TABLE "disclosures_investmentevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to investmentevent
--
ALTER TABLE "disclosures_investmentevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to investmentevent
--
ALTER TABLE "disclosures_investmentevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to giftevent
--
ALTER TABLE "disclosures_giftevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to giftevent
--
ALTER TABLE "disclosures_giftevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to giftevent
--
ALTER TABLE "disclosures_giftevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field person to financialdisclosureevent
--
ALTER TABLE "disclosures_financialdisclosureevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to financialdisclosureevent
--
ALTER TABLE "disclosures_financialdisclosureevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to financialdisclosureevent
--
ALTER TABLE "disclosures_financialdisclosureevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to debtevent
--
ALTER TABLE "disclosures_debtevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to debtevent
--
ALTER TABLE "disclosures_debtevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to debtevent
--
ALTER TABLE "disclosures_debtevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field financial_disclosure to agreementevent
--
ALTER TABLE "disclosures_agreementevent"
    ADD COLUMN "financial_disclosure_id" integer NOT NULL;
--
-- Add field pgh_context to agreementevent
--
ALTER TABLE "disclosures_agreementevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to agreementevent
--
ALTER TABLE "disclosures_agreementevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
CREATE INDEX "disclosures_spouseincomeevent_financial_disclosure_id_c0c5aac5" ON "disclosures_spouseincomeevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_spouseincomeevent_pgh_context_id_cc56881c" ON "disclosures_spouseincomeevent" ("pgh_context_id");
CREATE INDEX "disclosures_spouseincomeevent_pgh_obj_id_35eed7df" ON "disclosures_spouseincomeevent" ("pgh_obj_id");
CREATE INDEX "disclosures_reimbursementevent_financial_disclosure_id_c3e98e6a" ON "disclosures_reimbursementevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_reimbursementevent_pgh_context_id_bc88ae92" ON "disclosures_reimbursementevent" ("pgh_context_id");
CREATE INDEX "disclosures_reimbursementevent_pgh_obj_id_19ad4423" ON "disclosures_reimbursementevent" ("pgh_obj_id");
CREATE INDEX "disclosures_positionevent_financial_disclosure_id_ad3bcb32" ON "disclosures_positionevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_positionevent_pgh_context_id_f5ae70f1" ON "disclosures_positionevent" ("pgh_context_id");
CREATE INDEX "disclosures_positionevent_pgh_obj_id_41aaca6a" ON "disclosures_positionevent" ("pgh_obj_id");
CREATE INDEX "disclosures_noninvestmenti_financial_disclosure_id_9b4f08af" ON "disclosures_noninvestmentincomeevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_noninvestmentincomeevent_pgh_context_id_0497f781" ON "disclosures_noninvestmentincomeevent" ("pgh_context_id");
CREATE INDEX "disclosures_noninvestmentincomeevent_pgh_obj_id_a32a87a9" ON "disclosures_noninvestmentincomeevent" ("pgh_obj_id");
CREATE INDEX "disclosures_investmentevent_financial_disclosure_id_1692a34a" ON "disclosures_investmentevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_investmentevent_pgh_context_id_d04fb495" ON "disclosures_investmentevent" ("pgh_context_id");
CREATE INDEX "disclosures_investmentevent_pgh_obj_id_f8d5278d" ON "disclosures_investmentevent" ("pgh_obj_id");
CREATE INDEX "disclosures_giftevent_financial_disclosure_id_6da98fc4" ON "disclosures_giftevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_giftevent_pgh_context_id_e35c6eb6" ON "disclosures_giftevent" ("pgh_context_id");
CREATE INDEX "disclosures_giftevent_pgh_obj_id_59ce33d3" ON "disclosures_giftevent" ("pgh_obj_id");
CREATE INDEX "disclosures_financialdisclosureevent_person_id_6936f8d9" ON "disclosures_financialdisclosureevent" ("person_id");
CREATE INDEX "disclosures_financialdisclosureevent_pgh_context_id_83781350" ON "disclosures_financialdisclosureevent" ("pgh_context_id");
CREATE INDEX "disclosures_financialdisclosureevent_pgh_obj_id_c4ffefde" ON "disclosures_financialdisclosureevent" ("pgh_obj_id");
CREATE INDEX "disclosures_debtevent_financial_disclosure_id_98538f65" ON "disclosures_debtevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_debtevent_pgh_context_id_651400a2" ON "disclosures_debtevent" ("pgh_context_id");
CREATE INDEX "disclosures_debtevent_pgh_obj_id_11b68656" ON "disclosures_debtevent" ("pgh_obj_id");
CREATE INDEX "disclosures_agreementevent_financial_disclosure_id_c846388c" ON "disclosures_agreementevent" ("financial_disclosure_id");
CREATE INDEX "disclosures_agreementevent_pgh_context_id_b3cc1300" ON "disclosures_agreementevent" ("pgh_context_id");
CREATE INDEX "disclosures_agreementevent_pgh_obj_id_cdf3d4f8" ON "disclosures_agreementevent" ("pgh_obj_id");
COMMIT;
