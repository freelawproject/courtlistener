BEGIN;
--
-- Remove trigger snapshot_insert from model abarating
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_26a9a ON "people_db_abarating";
--
-- Remove trigger snapshot_update from model abarating
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1a35c ON "people_db_abarating";
--
-- Remove trigger snapshot_insert from model education
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3f5b7 ON "people_db_education";
--
-- Remove trigger snapshot_update from model education
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_342ab ON "people_db_education";
--
-- Remove trigger snapshot_insert from model person
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_271f6 ON "people_db_person";
--
-- Remove trigger snapshot_update from model person
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_11bc7 ON "people_db_person";
--
-- Remove trigger snapshot_insert from model personrace
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3bcce ON "people_db_person_race";
--
-- Remove trigger snapshot_update from model personrace
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_134c2 ON "people_db_person_race";
--
-- Remove trigger snapshot_insert from model politicalaffiliation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_ab32e ON "people_db_politicalaffiliation";
--
-- Remove trigger snapshot_update from model politicalaffiliation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6f60c ON "people_db_politicalaffiliation";
--
-- Remove trigger snapshot_insert from model position
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b594d ON "people_db_position";
--
-- Remove trigger snapshot_update from model position
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d5203 ON "people_db_position";
--
-- Remove trigger snapshot_insert from model race
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_36b13 ON "people_db_race";
--
-- Remove trigger snapshot_update from model race
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_901ca ON "people_db_race";
--
-- Remove trigger snapshot_insert from model retentionevent
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_123d1 ON "people_db_retentionevent";
--
-- Remove trigger snapshot_update from model retentionevent
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_21cad ON "people_db_retentionevent";
--
-- Remove trigger snapshot_insert from model school
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_79a6c ON "people_db_school";
--
-- Remove trigger snapshot_update from model school
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d61c7 ON "people_db_school";
--
-- Remove trigger snapshot_insert from model source
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c86e5 ON "people_db_source";
--
-- Remove trigger snapshot_update from model source
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6b08f ON "people_db_source";
--
-- Create trigger update_or_delete_snapshot_update on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_5d5cb()
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
    INSERT INTO "people_db_abaratingevent" ("date_created", "date_modified", "id", "person_id", "pgh_context_id",
                                            "pgh_created_at", "pgh_label", "pgh_obj_id", "rating", "year_rated")
    VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."rating", OLD."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_5d5cb ON "people_db_abarating";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_5d5cb
    AFTER UPDATE
    ON "people_db_abarating"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR OLD."year_rated" IS DISTINCT FROM NEW."year_rated" OR
          OLD."rating" IS DISTINCT FROM NEW."rating")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_5d5cb();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_5d5cb ON "people_db_abarating" IS 'b44f8e327179e87314466466ae565fe394b8513c';
;
--
-- Create trigger update_or_delete_snapshot_delete on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_9f6fd()
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
    INSERT INTO "people_db_abaratingevent" ("date_created", "date_modified", "id", "person_id", "pgh_context_id",
                                            "pgh_created_at", "pgh_label", "pgh_obj_id", "rating", "year_rated")
    VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."rating", OLD."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_9f6fd ON "people_db_abarating";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_9f6fd
    AFTER DELETE
    ON "people_db_abarating"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_9f6fd();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_9f6fd ON "people_db_abarating" IS 'f865183e7573427d166286d2aeb0c0e1fcf16d01';
;
--
-- Create trigger update_or_delete_snapshot_update on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_4e1c4()
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
    INSERT INTO "people_db_educationevent" ("date_created", "date_modified", "degree_detail", "degree_level",
                                            "degree_year", "id", "person_id", "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id", "school_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."degree_detail", OLD."degree_level", OLD."degree_year",
            OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_4e1c4 ON "people_db_education";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_4e1c4
    AFTER UPDATE
    ON "people_db_education"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR OLD."school_id" IS DISTINCT FROM NEW."school_id" OR
          OLD."degree_level" IS DISTINCT FROM NEW."degree_level" OR
          OLD."degree_detail" IS DISTINCT FROM NEW."degree_detail" OR
          OLD."degree_year" IS DISTINCT FROM NEW."degree_year")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_4e1c4();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_4e1c4 ON "people_db_education" IS '14de8b602f10474b6e9ba2e40db3a8917bb7974d';
;
--
-- Create trigger update_or_delete_snapshot_delete on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_bf937()
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
    INSERT INTO "people_db_educationevent" ("date_created", "date_modified", "degree_detail", "degree_level",
                                            "degree_year", "id", "person_id", "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id", "school_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."degree_detail", OLD."degree_level", OLD."degree_year",
            OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_bf937 ON "people_db_education";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_bf937
    AFTER DELETE
    ON "people_db_education"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_bf937();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_bf937 ON "people_db_education" IS '9a6f99da78762bcbe0545a84ea405ac1d971e2fc';
;
--
-- Create trigger update_or_delete_snapshot_update on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_0f619()
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
    INSERT INTO "people_db_personevent" ("date_completed", "date_created", "date_dob", "date_dod",
                                         "date_granularity_dob", "date_granularity_dod", "date_modified", "dob_city",
                                         "dob_country", "dob_state", "dod_city", "dod_country", "dod_state", "fjc_id",
                                         "ftm_eid", "ftm_total_received", "gender", "has_photo", "id", "is_alias_of_id",
                                         "name_first", "name_last", "name_middle", "name_suffix", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id", "religion", "slug")
    VALUES (OLD."date_completed", OLD."date_created", OLD."date_dob", OLD."date_dod", OLD."date_granularity_dob",
            OLD."date_granularity_dod", OLD."date_modified", OLD."dob_city", OLD."dob_country", OLD."dob_state",
            OLD."dod_city", OLD."dod_country", OLD."dod_state", OLD."fjc_id", OLD."ftm_eid", OLD."ftm_total_received",
            OLD."gender", OLD."has_photo", OLD."id", OLD."is_alias_of_id", OLD."name_first", OLD."name_last",
            OLD."name_middle", OLD."name_suffix", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."religion", OLD."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0f619 ON "people_db_person";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_0f619
    AFTER UPDATE
    ON "people_db_person"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."is_alias_of_id" IS DISTINCT FROM NEW."is_alias_of_id" OR
          OLD."date_completed" IS DISTINCT FROM NEW."date_completed" OR OLD."fjc_id" IS DISTINCT FROM NEW."fjc_id" OR
          OLD."slug" IS DISTINCT FROM NEW."slug" OR OLD."name_first" IS DISTINCT FROM NEW."name_first" OR
          OLD."name_middle" IS DISTINCT FROM NEW."name_middle" OR OLD."name_last" IS DISTINCT FROM NEW."name_last" OR
          OLD."name_suffix" IS DISTINCT FROM NEW."name_suffix" OR OLD."date_dob" IS DISTINCT FROM NEW."date_dob" OR
          OLD."date_granularity_dob" IS DISTINCT FROM NEW."date_granularity_dob" OR
          OLD."date_dod" IS DISTINCT FROM NEW."date_dod" OR
          OLD."date_granularity_dod" IS DISTINCT FROM NEW."date_granularity_dod" OR
          OLD."dob_city" IS DISTINCT FROM NEW."dob_city" OR OLD."dob_state" IS DISTINCT FROM NEW."dob_state" OR
          OLD."dob_country" IS DISTINCT FROM NEW."dob_country" OR OLD."dod_city" IS DISTINCT FROM NEW."dod_city" OR
          OLD."dod_state" IS DISTINCT FROM NEW."dod_state" OR OLD."dod_country" IS DISTINCT FROM NEW."dod_country" OR
          OLD."gender" IS DISTINCT FROM NEW."gender" OR OLD."religion" IS DISTINCT FROM NEW."religion" OR
          OLD."ftm_total_received" IS DISTINCT FROM NEW."ftm_total_received" OR
          OLD."ftm_eid" IS DISTINCT FROM NEW."ftm_eid" OR OLD."has_photo" IS DISTINCT FROM NEW."has_photo")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_0f619();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_0f619 ON "people_db_person" IS '3cdf59b7de68816d997aa47cfed6fbb4e41c2da5';
;
--
-- Create trigger update_or_delete_snapshot_delete on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_649cf()
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
    INSERT INTO "people_db_personevent" ("date_completed", "date_created", "date_dob", "date_dod",
                                         "date_granularity_dob", "date_granularity_dod", "date_modified", "dob_city",
                                         "dob_country", "dob_state", "dod_city", "dod_country", "dod_state", "fjc_id",
                                         "ftm_eid", "ftm_total_received", "gender", "has_photo", "id", "is_alias_of_id",
                                         "name_first", "name_last", "name_middle", "name_suffix", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id", "religion", "slug")
    VALUES (OLD."date_completed", OLD."date_created", OLD."date_dob", OLD."date_dod", OLD."date_granularity_dob",
            OLD."date_granularity_dod", OLD."date_modified", OLD."dob_city", OLD."dob_country", OLD."dob_state",
            OLD."dod_city", OLD."dod_country", OLD."dod_state", OLD."fjc_id", OLD."ftm_eid", OLD."ftm_total_received",
            OLD."gender", OLD."has_photo", OLD."id", OLD."is_alias_of_id", OLD."name_first", OLD."name_last",
            OLD."name_middle", OLD."name_suffix", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."religion", OLD."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_649cf ON "people_db_person";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_649cf
    AFTER DELETE
    ON "people_db_person"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_649cf();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_649cf ON "people_db_person" IS '0124a496982c3c63f186d9d8af372dbb97b476ea';
;
--
-- Create trigger update_or_delete_snapshot_update on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_d9c4d()
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
    INSERT INTO "people_db_personraceevent" ("id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                             "race_id")
    VALUES (OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_d9c4d ON "people_db_person_race";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_d9c4d
    AFTER UPDATE
    ON "people_db_person_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_d9c4d();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_d9c4d ON "people_db_person_race" IS 'e9b396c2a7e0eba486ceb421c26e54f6fe9e55ae';
;
--
-- Create trigger update_or_delete_snapshot_delete on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_c73dc()
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
    INSERT INTO "people_db_personraceevent" ("id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                             "race_id")
    VALUES (OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_c73dc ON "people_db_person_race";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_c73dc
    AFTER DELETE
    ON "people_db_person_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_c73dc();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_c73dc ON "people_db_person_race" IS '150298646b18b3d85f58e33b42e493b23fe6f646';
;
--
-- Create trigger update_or_delete_snapshot_update on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_54863()
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
    INSERT INTO "people_db_politicalaffiliationevent" ("date_created", "date_end", "date_granularity_end",
                                                       "date_granularity_start", "date_modified", "date_start", "id",
                                                       "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                                       "pgh_obj_id", "political_party", "source")
    VALUES (OLD."date_created", OLD."date_end", OLD."date_granularity_end", OLD."date_granularity_start",
            OLD."date_modified", OLD."date_start", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."political_party", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_54863 ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_54863
    AFTER UPDATE
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR
          OLD."political_party" IS DISTINCT FROM NEW."political_party" OR OLD."source" IS DISTINCT FROM NEW."source" OR
          OLD."date_start" IS DISTINCT FROM NEW."date_start" OR
          OLD."date_granularity_start" IS DISTINCT FROM NEW."date_granularity_start" OR
          OLD."date_end" IS DISTINCT FROM NEW."date_end" OR
          OLD."date_granularity_end" IS DISTINCT FROM NEW."date_granularity_end")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_54863();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_54863 ON "people_db_politicalaffiliation" IS 'f844652675919e213358f286c96440c5488e7930';
;
--
-- Create trigger update_or_delete_snapshot_delete on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_d036d()
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
    INSERT INTO "people_db_politicalaffiliationevent" ("date_created", "date_end", "date_granularity_end",
                                                       "date_granularity_start", "date_modified", "date_start", "id",
                                                       "person_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                                       "pgh_obj_id", "political_party", "source")
    VALUES (OLD."date_created", OLD."date_end", OLD."date_granularity_end", OLD."date_granularity_start",
            OLD."date_modified", OLD."date_start", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."political_party", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_d036d ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_d036d
    AFTER DELETE
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_d036d();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_d036d ON "people_db_politicalaffiliation" IS 'c192b5c62cfcf07e04e6a49ae97aaeb5ffd0d424';
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_0586a()
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
    INSERT INTO "people_db_positionevent" ("appointer_id", "court_id", "date_confirmation", "date_created",
                                           "date_elected", "date_granularity_start", "date_granularity_termination",
                                           "date_hearing", "date_judicial_committee_action", "date_modified",
                                           "date_nominated", "date_recess_appointment",
                                           "date_referred_to_judicial_committee", "date_retirement", "date_start",
                                           "date_termination", "has_inferred_values", "how_selected", "id", "job_title",
                                           "judicial_committee_action", "location_city", "location_state",
                                           "nomination_process", "organization_name", "person_id", "pgh_context_id",
                                           "pgh_created_at", "pgh_label", "pgh_obj_id", "position_type",
                                           "predecessor_id", "school_id", "sector", "supervisor_id",
                                           "termination_reason", "voice_vote", "vote_type", "votes_no",
                                           "votes_no_percent", "votes_yes", "votes_yes_percent")
    VALUES (OLD."appointer_id", OLD."court_id", OLD."date_confirmation", OLD."date_created", OLD."date_elected",
            OLD."date_granularity_start", OLD."date_granularity_termination", OLD."date_hearing",
            OLD."date_judicial_committee_action", OLD."date_modified", OLD."date_nominated",
            OLD."date_recess_appointment", OLD."date_referred_to_judicial_committee", OLD."date_retirement",
            OLD."date_start", OLD."date_termination", OLD."has_inferred_values", OLD."how_selected", OLD."id",
            OLD."job_title", OLD."judicial_committee_action", OLD."location_city", OLD."location_state",
            OLD."nomination_process", OLD."organization_name", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."position_type", OLD."predecessor_id", OLD."school_id",
            OLD."sector", OLD."supervisor_id", OLD."termination_reason", OLD."voice_vote", OLD."vote_type",
            OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0586a ON "people_db_position";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_0586a
    AFTER UPDATE
    ON "people_db_position"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."position_type" IS DISTINCT FROM NEW."position_type" OR
          OLD."job_title" IS DISTINCT FROM NEW."job_title" OR OLD."sector" IS DISTINCT FROM NEW."sector" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR OLD."court_id" IS DISTINCT FROM NEW."court_id" OR
          OLD."school_id" IS DISTINCT FROM NEW."school_id" OR
          OLD."organization_name" IS DISTINCT FROM NEW."organization_name" OR
          OLD."location_city" IS DISTINCT FROM NEW."location_city" OR
          OLD."location_state" IS DISTINCT FROM NEW."location_state" OR
          OLD."appointer_id" IS DISTINCT FROM NEW."appointer_id" OR
          OLD."supervisor_id" IS DISTINCT FROM NEW."supervisor_id" OR
          OLD."predecessor_id" IS DISTINCT FROM NEW."predecessor_id" OR
          OLD."date_nominated" IS DISTINCT FROM NEW."date_nominated" OR
          OLD."date_elected" IS DISTINCT FROM NEW."date_elected" OR
          OLD."date_recess_appointment" IS DISTINCT FROM NEW."date_recess_appointment" OR
          OLD."date_referred_to_judicial_committee" IS DISTINCT FROM NEW."date_referred_to_judicial_committee" OR
          OLD."date_judicial_committee_action" IS DISTINCT FROM NEW."date_judicial_committee_action" OR
          OLD."judicial_committee_action" IS DISTINCT FROM NEW."judicial_committee_action" OR
          OLD."date_hearing" IS DISTINCT FROM NEW."date_hearing" OR
          OLD."date_confirmation" IS DISTINCT FROM NEW."date_confirmation" OR
          OLD."date_start" IS DISTINCT FROM NEW."date_start" OR
          OLD."date_granularity_start" IS DISTINCT FROM NEW."date_granularity_start" OR
          OLD."date_termination" IS DISTINCT FROM NEW."date_termination" OR
          OLD."termination_reason" IS DISTINCT FROM NEW."termination_reason" OR
          OLD."date_granularity_termination" IS DISTINCT FROM NEW."date_granularity_termination" OR
          OLD."date_retirement" IS DISTINCT FROM NEW."date_retirement" OR
          OLD."nomination_process" IS DISTINCT FROM NEW."nomination_process" OR
          OLD."vote_type" IS DISTINCT FROM NEW."vote_type" OR OLD."voice_vote" IS DISTINCT FROM NEW."voice_vote" OR
          OLD."votes_yes" IS DISTINCT FROM NEW."votes_yes" OR OLD."votes_no" IS DISTINCT FROM NEW."votes_no" OR
          OLD."votes_yes_percent" IS DISTINCT FROM NEW."votes_yes_percent" OR
          OLD."votes_no_percent" IS DISTINCT FROM NEW."votes_no_percent" OR
          OLD."how_selected" IS DISTINCT FROM NEW."how_selected" OR
          OLD."has_inferred_values" IS DISTINCT FROM NEW."has_inferred_values")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_0586a();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_0586a ON "people_db_position" IS '7185484a444f4e71898879f5549b4bedf3f915fe';
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_ca371()
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
    INSERT INTO "people_db_positionevent" ("appointer_id", "court_id", "date_confirmation", "date_created",
                                           "date_elected", "date_granularity_start", "date_granularity_termination",
                                           "date_hearing", "date_judicial_committee_action", "date_modified",
                                           "date_nominated", "date_recess_appointment",
                                           "date_referred_to_judicial_committee", "date_retirement", "date_start",
                                           "date_termination", "has_inferred_values", "how_selected", "id", "job_title",
                                           "judicial_committee_action", "location_city", "location_state",
                                           "nomination_process", "organization_name", "person_id", "pgh_context_id",
                                           "pgh_created_at", "pgh_label", "pgh_obj_id", "position_type",
                                           "predecessor_id", "school_id", "sector", "supervisor_id",
                                           "termination_reason", "voice_vote", "vote_type", "votes_no",
                                           "votes_no_percent", "votes_yes", "votes_yes_percent")
    VALUES (OLD."appointer_id", OLD."court_id", OLD."date_confirmation", OLD."date_created", OLD."date_elected",
            OLD."date_granularity_start", OLD."date_granularity_termination", OLD."date_hearing",
            OLD."date_judicial_committee_action", OLD."date_modified", OLD."date_nominated",
            OLD."date_recess_appointment", OLD."date_referred_to_judicial_committee", OLD."date_retirement",
            OLD."date_start", OLD."date_termination", OLD."has_inferred_values", OLD."how_selected", OLD."id",
            OLD."job_title", OLD."judicial_committee_action", OLD."location_city", OLD."location_state",
            OLD."nomination_process", OLD."organization_name", OLD."person_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."position_type", OLD."predecessor_id", OLD."school_id",
            OLD."sector", OLD."supervisor_id", OLD."termination_reason", OLD."voice_vote", OLD."vote_type",
            OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_ca371 ON "people_db_position";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_ca371
    AFTER DELETE
    ON "people_db_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_ca371();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_ca371 ON "people_db_position" IS '37c3937046469b37e52aac1a4ddebd56e42a5a4f';
;
--
-- Create trigger update_or_delete_snapshot_update on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_a4b83()
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
    INSERT INTO "people_db_raceevent" ("id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "race")
    VALUES (OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_a4b83 ON "people_db_race";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_a4b83
    AFTER UPDATE
    ON "people_db_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_a4b83();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_a4b83 ON "people_db_race" IS '8d9f6a71b0465ca997d273d204aafa2c10689c6f';
;
--
-- Create trigger update_or_delete_snapshot_delete on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_f6fcc()
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
    INSERT INTO "people_db_raceevent" ("id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "race")
    VALUES (OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_f6fcc ON "people_db_race";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_f6fcc
    AFTER DELETE
    ON "people_db_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_f6fcc();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_f6fcc ON "people_db_race" IS '04b6ad1015070427b423239f7f7dc486e8453c75';
;
--
-- Create trigger update_or_delete_snapshot_update on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_ef1b8()
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
    INSERT INTO "people_db_retentioneventevent" ("date_created", "date_modified", "date_retention", "id",
                                                 "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                 "position_id", "retention_type", "unopposed", "votes_no",
                                                 "votes_no_percent", "votes_yes", "votes_yes_percent", "won")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_retention", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."position_id", OLD."retention_type", OLD."unopposed",
            OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent", OLD."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ef1b8 ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_ef1b8
    AFTER UPDATE
    ON "people_db_retentionevent"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."position_id" IS DISTINCT FROM NEW."position_id" OR
          OLD."retention_type" IS DISTINCT FROM NEW."retention_type" OR
          OLD."date_retention" IS DISTINCT FROM NEW."date_retention" OR
          OLD."votes_yes" IS DISTINCT FROM NEW."votes_yes" OR OLD."votes_no" IS DISTINCT FROM NEW."votes_no" OR
          OLD."votes_yes_percent" IS DISTINCT FROM NEW."votes_yes_percent" OR
          OLD."votes_no_percent" IS DISTINCT FROM NEW."votes_no_percent" OR
          OLD."unopposed" IS DISTINCT FROM NEW."unopposed" OR OLD."won" IS DISTINCT FROM NEW."won")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_ef1b8();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_ef1b8 ON "people_db_retentionevent" IS '3ab69ed2974e13925bfb60fff196b490d8e909dd';
;
--
-- Create trigger update_or_delete_snapshot_delete on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_f0c63()
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
    INSERT INTO "people_db_retentioneventevent" ("date_created", "date_modified", "date_retention", "id",
                                                 "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                 "position_id", "retention_type", "unopposed", "votes_no",
                                                 "votes_no_percent", "votes_yes", "votes_yes_percent", "won")
    VALUES (OLD."date_created", OLD."date_modified", OLD."date_retention", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."id", OLD."position_id", OLD."retention_type", OLD."unopposed",
            OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent", OLD."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_f0c63 ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_f0c63
    AFTER DELETE
    ON "people_db_retentionevent"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_f0c63();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_f0c63 ON "people_db_retentionevent" IS 'ffbb1483333a4f0661e087cd2c5a915c1ec73d62';
;
--
-- Create trigger update_or_delete_snapshot_update on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_471f3()
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
    INSERT INTO "people_db_schoolevent" ("date_created", "date_modified", "ein", "id", "is_alias_of_id", "name",
                                         "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."ein", OLD."id", OLD."is_alias_of_id", OLD."name",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_471f3 ON "people_db_school";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_471f3
    AFTER UPDATE
    ON "people_db_school"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."is_alias_of_id" IS DISTINCT FROM NEW."is_alias_of_id" OR OLD."name" IS DISTINCT FROM NEW."name" OR
          OLD."ein" IS DISTINCT FROM NEW."ein")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_471f3();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_471f3 ON "people_db_school" IS 'f2a0bb13e8fb9f5a5e86ea76039d6d2146264d1f';
;
--
-- Create trigger update_or_delete_snapshot_delete on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_40dc2()
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
    INSERT INTO "people_db_schoolevent" ("date_created", "date_modified", "ein", "id", "is_alias_of_id", "name",
                                         "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."ein", OLD."id", OLD."is_alias_of_id", OLD."name",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_40dc2 ON "people_db_school";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_40dc2
    AFTER DELETE
    ON "people_db_school"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_40dc2();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_40dc2 ON "people_db_school" IS '58acc759771efced22d98781d51e16b70e962b12';
;
--
-- Create trigger update_or_delete_snapshot_update on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_88fe4()
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
    INSERT INTO "people_db_sourceevent" ("date_accessed", "date_created", "date_modified", "id", "notes", "person_id",
                                         "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url")
    VALUES (OLD."date_accessed", OLD."date_created", OLD."date_modified", OLD."id", OLD."notes", OLD."person_id",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_88fe4 ON "people_db_source";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_88fe4
    AFTER UPDATE
    ON "people_db_source"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."person_id" IS DISTINCT FROM NEW."person_id" OR OLD."url" IS DISTINCT FROM NEW."url" OR
          OLD."date_accessed" IS DISTINCT FROM NEW."date_accessed" OR OLD."notes" IS DISTINCT FROM NEW."notes")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_88fe4();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_88fe4 ON "people_db_source" IS 'd691f1f3a5c8572a4f8989381817719d6e727254';
;
--
-- Create trigger update_or_delete_snapshot_delete on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_1db27()
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
    INSERT INTO "people_db_sourceevent" ("date_accessed", "date_created", "date_modified", "id", "notes", "person_id",
                                         "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url")
    VALUES (OLD."date_accessed", OLD."date_created", OLD."date_modified", OLD."id", OLD."notes", OLD."person_id",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_1db27 ON "people_db_source";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_1db27
    AFTER DELETE
    ON "people_db_source"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_1db27();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_1db27 ON "people_db_source" IS 'af8df2f3c5785a341684b95deac86682455ca38a';
;
COMMIT;
