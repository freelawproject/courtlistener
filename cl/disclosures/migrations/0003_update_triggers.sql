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
-- Create trigger update_or_delete_snapshot_update on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_65f1b()
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
            OLD."parties_and_terms", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_65f1b ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_65f1b
    AFTER UPDATE
    ON "disclosures_agreement"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."date_raw" IS DISTINCT FROM NEW."date_raw" OR
          OLD."parties_and_terms" IS DISTINCT FROM NEW."parties_and_terms" OR
          OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_65f1b();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_65f1b ON "disclosures_agreement" IS '73f864bd17a4901dabdc71019b29c77031da8337';
;
--
-- Create trigger update_or_delete_snapshot_delete on model agreement
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_ae9c8()
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
            OLD."parties_and_terms", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_ae9c8 ON "disclosures_agreement";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_ae9c8
    AFTER DELETE
    ON "disclosures_agreement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_ae9c8();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_ae9c8 ON "disclosures_agreement" IS '2c3ba10e5850da2811f2dde8e5dda3e1a59c130c';
;
--
-- Create trigger update_or_delete_snapshot_update on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_babdd()
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
            OLD."financial_disclosure_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."redacted", OLD."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_babdd ON "disclosures_debt";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_babdd
    AFTER UPDATE
    ON "disclosures_debt"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."creditor_name" IS DISTINCT FROM NEW."creditor_name" OR
          OLD."description" IS DISTINCT FROM NEW."description" OR OLD."value_code" IS DISTINCT FROM NEW."value_code" OR
          OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_babdd();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_babdd ON "disclosures_debt" IS '36bc527745c0e12f96523daa42231ab4d179d1a2';
;
--
-- Create trigger update_or_delete_snapshot_delete on model debt
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_93756()
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
            OLD."financial_disclosure_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."redacted", OLD."value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_93756 ON "disclosures_debt";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_93756
    AFTER DELETE
    ON "disclosures_debt"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_93756();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_93756 ON "disclosures_debt" IS '2d6cf45df4e9c8e014ddf857e0290445b9b5267f';
;
--
-- Create trigger update_or_delete_snapshot_update on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_4f47a()
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
            OLD."page_count", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."report_type", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status", OLD."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_4f47a ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_4f47a
    AFTER UPDATE
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR OLD."year" IS DISTINCT FROM NEW."year" OR
          OLD."download_filepath" IS DISTINCT FROM NEW."download_filepath" OR
          OLD."filepath" IS DISTINCT FROM NEW."filepath" OR OLD."thumbnail" IS DISTINCT FROM NEW."thumbnail" OR
          OLD."thumbnail_status" IS DISTINCT FROM NEW."thumbnail_status" OR
          OLD."page_count" IS DISTINCT FROM NEW."page_count" OR OLD."sha1" IS DISTINCT FROM NEW."sha1" OR
          OLD."report_type" IS DISTINCT FROM NEW."report_type" OR OLD."is_amended" IS DISTINCT FROM NEW."is_amended" OR
          OLD."addendum_content_raw" IS DISTINCT FROM NEW."addendum_content_raw" OR
          OLD."addendum_redacted" IS DISTINCT FROM NEW."addendum_redacted" OR
          OLD."has_been_extracted" IS DISTINCT FROM NEW."has_been_extracted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_4f47a();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_4f47a ON "disclosures_financialdisclosure" IS 'a0e2dbb63a8f055a03df32f7b566f1edf3d03d58';
;
--
-- Create trigger update_or_delete_snapshot_delete on model financialdisclosure
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_40113()
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
            OLD."page_count", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."report_type", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status", OLD."year");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_40113 ON "disclosures_financialdisclosure";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_40113
    AFTER DELETE
    ON "disclosures_financialdisclosure"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_40113();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_40113 ON "disclosures_financialdisclosure" IS '4a2077474bd643761eaeb1af3a9a5275bc5017ab';
;
--
-- Create trigger update_or_delete_snapshot_update on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_63936()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."source",
            OLD."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_63936 ON "disclosures_gift";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_63936
    AFTER UPDATE
    ON "disclosures_gift"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."source" IS DISTINCT FROM NEW."source" OR OLD."description" IS DISTINCT FROM NEW."description" OR
          OLD."value" IS DISTINCT FROM NEW."value" OR OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_63936();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_63936 ON "disclosures_gift" IS '1fbd5a48f9d799cb1696409261368d75bacd7557';
;
--
-- Create trigger update_or_delete_snapshot_delete on model gift
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_12676()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."source",
            OLD."value");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_12676 ON "disclosures_gift";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_12676
    AFTER DELETE
    ON "disclosures_gift"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_12676();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_12676 ON "disclosures_gift" IS '916cc1e7591a3850b14e8564448f20117527f31e';
;
--
-- Create trigger update_or_delete_snapshot_update on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_a066d()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."transaction_date",
            OLD."transaction_date_raw", OLD."transaction_during_reporting_period", OLD."transaction_gain_code",
            OLD."transaction_partner", OLD."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_a066d ON "disclosures_investment";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_a066d
    AFTER UPDATE
    ON "disclosures_investment"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."page_number" IS DISTINCT FROM NEW."page_number" OR
          OLD."description" IS DISTINCT FROM NEW."description" OR OLD."redacted" IS DISTINCT FROM NEW."redacted" OR
          OLD."income_during_reporting_period_code" IS DISTINCT FROM NEW."income_during_reporting_period_code" OR
          OLD."income_during_reporting_period_type" IS DISTINCT FROM NEW."income_during_reporting_period_type" OR
          OLD."gross_value_code" IS DISTINCT FROM NEW."gross_value_code" OR
          OLD."gross_value_method" IS DISTINCT FROM NEW."gross_value_method" OR
          OLD."transaction_during_reporting_period" IS DISTINCT FROM NEW."transaction_during_reporting_period" OR
          OLD."transaction_date_raw" IS DISTINCT FROM NEW."transaction_date_raw" OR
          OLD."transaction_date" IS DISTINCT FROM NEW."transaction_date" OR
          OLD."transaction_value_code" IS DISTINCT FROM NEW."transaction_value_code" OR
          OLD."transaction_gain_code" IS DISTINCT FROM NEW."transaction_gain_code" OR
          OLD."transaction_partner" IS DISTINCT FROM NEW."transaction_partner" OR
          OLD."has_inferred_values" IS DISTINCT FROM NEW."has_inferred_values")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_a066d();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_a066d ON "disclosures_investment" IS '44d13445ef620bd34ef9cb2cafc0a9e337282916';
;
--
-- Create trigger update_or_delete_snapshot_delete on model investment
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_7aa0d()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."transaction_date",
            OLD."transaction_date_raw", OLD."transaction_during_reporting_period", OLD."transaction_gain_code",
            OLD."transaction_partner", OLD."transaction_value_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_7aa0d ON "disclosures_investment";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_7aa0d
    AFTER DELETE
    ON "disclosures_investment"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_7aa0d();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_7aa0d ON "disclosures_investment" IS 'fe42d0a864a4320f67d8961f2737b28d83b175af';
;
--
-- Create trigger update_or_delete_snapshot_update on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_c0f2b()
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
            OLD."income_amount", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted",
            OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_c0f2b ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_c0f2b
    AFTER UPDATE
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."date_raw" IS DISTINCT FROM NEW."date_raw" OR OLD."source_type" IS DISTINCT FROM NEW."source_type" OR
          OLD."income_amount" IS DISTINCT FROM NEW."income_amount" OR OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_c0f2b();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_c0f2b ON "disclosures_noninvestmentincome" IS '21a9dff17a4c23244183f9bf818297c0df8df53c';
;
--
-- Create trigger update_or_delete_snapshot_delete on model noninvestmentincome
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_5213c()
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
            OLD."income_amount", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted",
            OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_5213c ON "disclosures_noninvestmentincome";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_5213c
    AFTER DELETE
    ON "disclosures_noninvestmentincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_5213c();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_5213c ON "disclosures_noninvestmentincome" IS '097868af34107a5d5532e1eb3e8f9043cee7faae';
;
--
-- Create trigger update_or_delete_snapshot_update on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_4daab()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."position", OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_4daab ON "disclosures_position";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_4daab
    AFTER UPDATE
    ON "disclosures_position"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."position" IS DISTINCT FROM NEW."position" OR
          OLD."organization_name" IS DISTINCT FROM NEW."organization_name" OR
          OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_4daab();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_4daab ON "disclosures_position" IS '38bff9355cac9268dd1e9816af7d38db3398a49e';
;
--
-- Create trigger update_or_delete_snapshot_delete on model position
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_3ce99()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."position", OLD."redacted");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_3ce99 ON "disclosures_position";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_3ce99
    AFTER DELETE
    ON "disclosures_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_3ce99();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_3ce99 ON "disclosures_position" IS 'a2292611d7a79c7a301ec1159b45e9fdcac0a3c6';
;
--
-- Create trigger update_or_delete_snapshot_update on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_c4cb9()
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
            OLD."items_paid_or_provided", OLD."location", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."purpose", OLD."redacted", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_c4cb9 ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_c4cb9
    AFTER UPDATE
    ON "disclosures_reimbursement"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."source" IS DISTINCT FROM NEW."source" OR OLD."date_raw" IS DISTINCT FROM NEW."date_raw" OR
          OLD."location" IS DISTINCT FROM NEW."location" OR OLD."purpose" IS DISTINCT FROM NEW."purpose" OR
          OLD."items_paid_or_provided" IS DISTINCT FROM NEW."items_paid_or_provided" OR
          OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_c4cb9();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_c4cb9 ON "disclosures_reimbursement" IS '33375f55f486414726a1e8a10f75c98265d65ae8';
;
--
-- Create trigger update_or_delete_snapshot_delete on model reimbursement
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_45e6c()
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
            OLD."items_paid_or_provided", OLD."location", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."purpose", OLD."redacted", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_45e6c ON "disclosures_reimbursement";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_45e6c
    AFTER DELETE
    ON "disclosures_reimbursement"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_45e6c();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_45e6c ON "disclosures_reimbursement" IS '41a46dd702cf60f7932c2d63fe6958e887fa9a95';
;
--
-- Create trigger update_or_delete_snapshot_update on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_dbb55()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_dbb55 ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_dbb55
    AFTER UPDATE
    ON "disclosures_spouseincome"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."financial_disclosure_id" IS DISTINCT FROM NEW."financial_disclosure_id" OR
          OLD."source_type" IS DISTINCT FROM NEW."source_type" OR OLD."date_raw" IS DISTINCT FROM NEW."date_raw" OR
          OLD."redacted" IS DISTINCT FROM NEW."redacted")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_dbb55();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_dbb55 ON "disclosures_spouseincome" IS 'e06fa4cc3078ade293dd0543ec39cb3c93b25ed8';
;
--
-- Create trigger update_or_delete_snapshot_delete on model spouseincome
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_9f215()
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
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."redacted", OLD."source_type");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_9f215 ON "disclosures_spouseincome";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_9f215
    AFTER DELETE
    ON "disclosures_spouseincome"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_9f215();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_9f215 ON "disclosures_spouseincome" IS '9a9f7ec8117ccc3050fed23b0303142d8e118fae';
;
COMMIT;
