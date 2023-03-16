BEGIN;
--
-- Remove trigger snapshot_insert from model agreement
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_69a8c ON "disclosures_agreement";
--
-- Remove trigger snapshot_update from model agreement
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_e00c2 ON "disclosures_agreement";
--
-- Remove trigger snapshot_insert from model debt
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_684e3 ON "disclosures_debt";
--
-- Remove trigger snapshot_update from model debt
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_93edc ON "disclosures_debt";
--
-- Remove trigger snapshot_insert from model financialdisclosure
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_64c14 ON "disclosures_financialdisclosure";
--
-- Remove trigger snapshot_update from model financialdisclosure
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_28e98 ON "disclosures_financialdisclosure";
--
-- Remove trigger snapshot_insert from model gift
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_94042 ON "disclosures_gift";
--
-- Remove trigger snapshot_update from model gift
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_9e72b ON "disclosures_gift";
--
-- Remove trigger snapshot_insert from model investment
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cde17 ON "disclosures_investment";
--
-- Remove trigger snapshot_update from model investment
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_f6320 ON "disclosures_investment";
--
-- Remove trigger snapshot_insert from model noninvestmentincome
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c76a9 ON "disclosures_noninvestmentincome";
--
-- Remove trigger snapshot_update from model noninvestmentincome
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_4b46e ON "disclosures_noninvestmentincome";
--
-- Remove trigger snapshot_insert from model position
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c33c6 ON "disclosures_position";
--
-- Remove trigger snapshot_update from model position
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6dbf5 ON "disclosures_position";
--
-- Remove trigger snapshot_insert from model reimbursement
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c2f93 ON "disclosures_reimbursement";
--
-- Remove trigger snapshot_update from model reimbursement
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_53701 ON "disclosures_reimbursement";
--
-- Remove trigger snapshot_insert from model spouseincome
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_5505f ON "disclosures_spouseincome";
--
-- Remove trigger snapshot_update from model spouseincome
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_37f1c ON "disclosures_spouseincome";
--
-- Create trigger custom_snapshot_insert on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_060c9()
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
    INSERT INTO "disclosures_agreementevent" ("date_created", "date_modified", "date_raw", "financial_disclosure_id",
                                              "id", "parties_and_terms", "pgh_context_id", "pgh_created_at",
                                              "pgh_label", "pgh_obj_id", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw", NEW."financial_disclosure_id", NEW."id",
            NEW."parties_and_terms", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_060c9 ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_060c9
    AFTER INSERT
    ON "disclosures_agreement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_060c9();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_060c9 ON "disclosures_agreement" IS '5a56075dfa625b635cf1505cf84f296aac00f975';
;
--
-- Create trigger custom_snapshot_update on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_02c65()
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
    INSERT INTO "disclosures_agreementevent" ("date_created", "date_modified", "date_raw", "financial_disclosure_id",
                                              "id", "parties_and_terms", "pgh_context_id", "pgh_created_at",
                                              "pgh_label", "pgh_obj_id", "redacted")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_raw", OLD."financial_disclosure_id", OLD."id",
            OLD."parties_and_terms", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_02c65 ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_custom_snapshot_update_02c65
    AFTER UPDATE
    ON "disclosures_agreement"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_02c65();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_02c65 ON "disclosures_agreement" IS 'e555ba91dbb5564616a341f7e72e25a862527c3a';
;
--
-- Create trigger custom_snapshot_insert on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_a3213()
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
    INSERT INTO "disclosures_debtevent" ("creditor_name", "date_created", "date_modified", "description",
                                         "financial_disclosure_id", "id", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted", "value_code")
    VALUES (NEW."creditor_name", NEW."date_created", NEW."date_modified", NEW."description",
            NEW."financial_disclosure_id", NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."redacted", NEW."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_a3213 ON "disclosures_debt";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_a3213
    AFTER INSERT
    ON "disclosures_debt"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_a3213();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_a3213 ON "disclosures_debt" IS '50ba25bba13d9876582a93009d7a175d32e96c8d';
;
--
-- Create trigger custom_snapshot_update on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_3bd4e()
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
    INSERT INTO "disclosures_debtevent" ("creditor_name", "date_created", "date_modified", "description",
                                         "financial_disclosure_id", "id", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "redacted", "value_code")
    VALUES (OLD."creditor_name", OLD."date_created", OLD."date_modified", OLD."description",
            OLD."financial_disclosure_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."redacted", OLD."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_3bd4e ON "disclosures_debt";
CREATE TRIGGER pgtrigger_custom_snapshot_update_3bd4e
    AFTER UPDATE
    ON "disclosures_debt"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_3bd4e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_3bd4e ON "disclosures_debt" IS 'f6a4e4405feb43218cb2decfe6554aec653b6152';
;
--
-- Create trigger custom_snapshot_insert on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_c180d()
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
    INSERT INTO "disclosures_financialdisclosureevent" ("addendum_content_raw", "addendum_redacted", "date_created",
                                                        "date_modified", "download_filepath", "filepath",
                                                        "has_been_extracted", "id", "is_amended", "page_count",
                                                        "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "report_type", "sha1", "thumbnail",
                                                        "thumbnail_status", "year")
    VALUES (NEW."addendum_content_raw", NEW."addendum_redacted", NEW."date_created", NEW."date_modified",
            NEW."download_filepath", NEW."filepath", NEW."has_been_extracted", NEW."id", NEW."is_amended",
            NEW."page_count", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."report_type", NEW."sha1", NEW."thumbnail", NEW."thumbnail_status", NEW."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_c180d ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_c180d
    AFTER INSERT
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_c180d();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_c180d ON "disclosures_financialdisclosure" IS 'afde16c3f6debcf10296d9c820b9b63b6c0cc64c';
;
--
-- Create trigger custom_snapshot_update on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_d66d5()
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
    INSERT INTO "disclosures_financialdisclosureevent" ("addendum_content_raw", "addendum_redacted", "date_created",
                                                        "date_modified", "download_filepath", "filepath",
                                                        "has_been_extracted", "id", "is_amended", "page_count",
                                                        "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                                        "pgh_obj_id", "report_type", "sha1", "thumbnail",
                                                        "thumbnail_status", "year")
    VALUES (OLD."addendum_content_raw", OLD."addendum_redacted", OLD."date_created", OLD."date_modified",
            OLD."download_filepath", OLD."filepath", OLD."has_been_extracted", OLD."id", OLD."is_amended",
            OLD."page_count", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."report_type", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status", OLD."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_d66d5 ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_custom_snapshot_update_d66d5
    AFTER UPDATE
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_d66d5();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_d66d5 ON "disclosures_financialdisclosure" IS 'b1ba35407a8f5e96c7124e06625755d19b1c3ef7';
;
--
-- Create trigger custom_snapshot_insert on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_7be22()
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
    INSERT INTO "disclosures_giftevent" ("date_created", "date_modified", "description", "financial_disclosure_id",
                                         "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                         "redacted", "source", "value")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description", NEW."financial_disclosure_id", NEW."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."redacted", NEW."source", NEW."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_7be22 ON "disclosures_gift";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_7be22
    AFTER INSERT
    ON "disclosures_gift"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_7be22();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_7be22 ON "disclosures_gift" IS '74897c41d509d4dd727dee4b1171dea5e5463839';
;
--
-- Create trigger custom_snapshot_update on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_a8157()
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
    INSERT INTO "disclosures_giftevent" ("date_created", "date_modified", "description", "financial_disclosure_id",
                                         "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                         "redacted", "source", "value")
    VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."financial_disclosure_id", OLD."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."redacted", OLD."source", OLD."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_a8157 ON "disclosures_gift";
CREATE TRIGGER pgtrigger_custom_snapshot_update_a8157
    AFTER UPDATE
    ON "disclosures_gift"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_a8157();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_a8157 ON "disclosures_gift" IS 'f017aeea4e1ee8d02eaf46115d4697a02a95c62a';
;
--
-- Create trigger custom_snapshot_insert on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_0a550()
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
    INSERT INTO "disclosures_investmentevent" ("date_created", "date_modified", "description",
                                               "financial_disclosure_id", "gross_value_code", "gross_value_method",
                                               "has_inferred_values", "id", "income_during_reporting_period_code",
                                               "income_during_reporting_period_type", "page_number", "pgh_context_id",
                                               "pgh_created_at", "pgh_label", "pgh_obj_id", "redacted",
                                               "transaction_date", "transaction_date_raw",
                                               "transaction_during_reporting_period", "transaction_gain_code",
                                               "transaction_partner", "transaction_value_code")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description", NEW."financial_disclosure_id",
            NEW."gross_value_code", NEW."gross_value_method", NEW."has_inferred_values", NEW."id",
            NEW."income_during_reporting_period_code", NEW."income_during_reporting_period_type", NEW."page_number",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."redacted", NEW."transaction_date",
            NEW."transaction_date_raw", NEW."transaction_during_reporting_period", NEW."transaction_gain_code",
            NEW."transaction_partner", NEW."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_0a550 ON "disclosures_investment";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_0a550
    AFTER INSERT
    ON "disclosures_investment"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_0a550();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_0a550 ON "disclosures_investment" IS '8e5f8db7fc234680557bf9fe6a17a56b2ae2bd22';
;
--
-- Create trigger custom_snapshot_update on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_440ee()
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
    INSERT INTO "disclosures_investmentevent" ("date_created", "date_modified", "description",
                                               "financial_disclosure_id", "gross_value_code", "gross_value_method",
                                               "has_inferred_values", "id", "income_during_reporting_period_code",
                                               "income_during_reporting_period_type", "page_number", "pgh_context_id",
                                               "pgh_created_at", "pgh_label", "pgh_obj_id", "redacted",
                                               "transaction_date", "transaction_date_raw",
                                               "transaction_during_reporting_period", "transaction_gain_code",
                                               "transaction_partner", "transaction_value_code")
    VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."financial_disclosure_id",
            OLD."gross_value_code", OLD."gross_value_method", OLD."has_inferred_values", OLD."id",
            OLD."income_during_reporting_period_code", OLD."income_during_reporting_period_type", OLD."page_number",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."redacted", OLD."transaction_date",
            OLD."transaction_date_raw", OLD."transaction_during_reporting_period", OLD."transaction_gain_code",
            OLD."transaction_partner", OLD."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_440ee ON "disclosures_investment";
CREATE TRIGGER pgtrigger_custom_snapshot_update_440ee
    AFTER UPDATE
    ON "disclosures_investment"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_440ee();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_440ee ON "disclosures_investment" IS '099292bc3958706d7bf0b19dfc76a831e31005c8';
;
--
-- Create trigger custom_snapshot_insert on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_1b22e()
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
    INSERT INTO "disclosures_noninvestmentincomeevent" ("date_created", "date_modified", "date_raw",
                                                        "financial_disclosure_id", "id", "income_amount",
                                                        "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                        "redacted", "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw", NEW."financial_disclosure_id", NEW."id",
            NEW."income_amount", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."redacted",
            NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_1b22e ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_1b22e
    AFTER INSERT
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_1b22e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_1b22e ON "disclosures_noninvestmentincome" IS '5652c43b0f4326cc8eeaaecc0ba9c7f4475fc23f';
;
--
-- Create trigger custom_snapshot_update on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_4adf3()
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
    INSERT INTO "disclosures_noninvestmentincomeevent" ("date_created", "date_modified", "date_raw",
                                                        "financial_disclosure_id", "id", "income_amount",
                                                        "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                        "redacted", "source_type")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_raw", OLD."financial_disclosure_id", OLD."id",
            OLD."income_amount", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."redacted",
            OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_4adf3 ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_custom_snapshot_update_4adf3
    AFTER UPDATE
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_4adf3();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_4adf3 ON "disclosures_noninvestmentincome" IS '12efe25e6d0a0d6281f71402b9b555aaed80d010';
;
--
-- Create trigger custom_snapshot_insert on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_9ebfd()
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
    INSERT INTO "disclosures_positionevent" ("date_created", "date_modified", "financial_disclosure_id", "id",
                                             "organization_name", "pgh_context_id", "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "position", "redacted")
    VALUES (NEW."date_created", NEW."date_modified", NEW."financial_disclosure_id", NEW."id", NEW."organization_name",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."position", NEW."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_9ebfd ON "disclosures_position";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_9ebfd
    AFTER INSERT
    ON "disclosures_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_9ebfd();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_9ebfd ON "disclosures_position" IS '5b3891591301d5379823fd701bab97256b037a1d';
;
--
-- Create trigger custom_snapshot_update on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_908be()
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
    INSERT INTO "disclosures_positionevent" ("date_created", "date_modified", "financial_disclosure_id", "id",
                                             "organization_name", "pgh_context_id", "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "position", "redacted")
    VALUES (OLD."date_created", OLD."date_modified", OLD."financial_disclosure_id", OLD."id", OLD."organization_name",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."position", OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_908be ON "disclosures_position";
CREATE TRIGGER pgtrigger_custom_snapshot_update_908be
    AFTER UPDATE
    ON "disclosures_position"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_908be();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_908be ON "disclosures_position" IS 'ef7e5702222b17b1826f252778014a1307e3e0fd';
;
--
-- Create trigger custom_snapshot_insert on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_40cd8()
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
    INSERT INTO "disclosures_reimbursementevent" ("date_created", "date_modified", "date_raw",
                                                  "financial_disclosure_id", "id", "items_paid_or_provided", "location",
                                                  "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                  "purpose", "redacted", "source")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw", NEW."financial_disclosure_id", NEW."id",
            NEW."items_paid_or_provided", NEW."location", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."purpose", NEW."redacted", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_40cd8 ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_40cd8
    AFTER INSERT
    ON "disclosures_reimbursement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_40cd8();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_40cd8 ON "disclosures_reimbursement" IS '3fbd7e2f16f7123f4a3fed1d52ec9beb59a49445';
;
--
-- Create trigger custom_snapshot_update on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_fa704()
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
    INSERT INTO "disclosures_reimbursementevent" ("date_created", "date_modified", "date_raw",
                                                  "financial_disclosure_id", "id", "items_paid_or_provided", "location",
                                                  "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                  "purpose", "redacted", "source")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_raw", OLD."financial_disclosure_id", OLD."id",
            OLD."items_paid_or_provided", OLD."location", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."purpose", OLD."redacted", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_fa704 ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_custom_snapshot_update_fa704
    AFTER UPDATE
    ON "disclosures_reimbursement"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_fa704();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_fa704 ON "disclosures_reimbursement" IS 'bb7f98ee839fe9ec3c4f198b6ef0954e262aded1';
;
--
-- Create trigger custom_snapshot_insert on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_01662()
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
    INSERT INTO "disclosures_spouseincomeevent" ("date_created", "date_modified", "date_raw", "financial_disclosure_id",
                                                 "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                 "redacted", "source_type")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_raw", NEW."financial_disclosure_id", NEW."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."redacted", NEW."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_01662 ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_01662
    AFTER INSERT
    ON "disclosures_spouseincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_01662();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_01662 ON "disclosures_spouseincome" IS '8f53becb619a5e28ff44938ef5af871d5f861de5';
;
--
-- Create trigger custom_snapshot_update on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_049d4()
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
    INSERT INTO "disclosures_spouseincomeevent" ("date_created", "date_modified", "date_raw", "financial_disclosure_id",
                                                 "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                 "redacted", "source_type")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_raw", OLD."financial_disclosure_id", OLD."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."redacted", OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_049d4 ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_custom_snapshot_update_049d4
    AFTER UPDATE
    ON "disclosures_spouseincome"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_049d4();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_049d4 ON "disclosures_spouseincome" IS '8824cee8d1676381ff1bd348f578b57bfde27050';
;
COMMIT;
