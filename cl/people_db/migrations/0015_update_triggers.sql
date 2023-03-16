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
-- Create trigger custom_snapshot_insert on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_1115f()
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
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id", NEW."rating", NEW."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_1115f ON "people_db_abarating";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_1115f
    AFTER INSERT
    ON "people_db_abarating"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_1115f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_1115f ON "people_db_abarating" IS '2978f3d8c124c0a91979e5e2ac9ba546b8a57961';
;
--
-- Create trigger custom_snapshot_update on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_22ecc()
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
            'custom_snapshot', OLD."id", OLD."rating", OLD."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_22ecc ON "people_db_abarating";
CREATE TRIGGER pgtrigger_custom_snapshot_update_22ecc
    AFTER UPDATE
    ON "people_db_abarating"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_22ecc();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_22ecc ON "people_db_abarating" IS '9df80b34e689a97c0db2b7a632b857ea86da6897';
;
--
-- Create trigger custom_snapshot_insert on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_48316()
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
    VALUES (NEW."date_created", NEW."date_modified", NEW."degree_detail", NEW."degree_level", NEW."degree_year",
            NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_48316 ON "people_db_education";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_48316
    AFTER INSERT
    ON "people_db_education"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_48316();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_48316 ON "people_db_education" IS 'c672b5a67592087c7245b54831eb6c7557d8f769';
;
--
-- Create trigger custom_snapshot_update on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_5d60e()
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
            OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_5d60e ON "people_db_education";
CREATE TRIGGER pgtrigger_custom_snapshot_update_5d60e
    AFTER UPDATE
    ON "people_db_education"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_5d60e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_5d60e ON "people_db_education" IS '5d89a4d6dcbbcc589a75c5ab58925b79bc126c33';
;
--
-- Create trigger custom_snapshot_insert on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_a2f87()
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
    VALUES (NEW."date_completed", NEW."date_created", NEW."date_dob", NEW."date_dod", NEW."date_granularity_dob",
            NEW."date_granularity_dod", NEW."date_modified", NEW."dob_city", NEW."dob_country", NEW."dob_state",
            NEW."dod_city", NEW."dod_country", NEW."dod_state", NEW."fjc_id", NEW."ftm_eid", NEW."ftm_total_received",
            NEW."gender", NEW."has_photo", NEW."id", NEW."is_alias_of_id", NEW."name_first", NEW."name_last",
            NEW."name_middle", NEW."name_suffix", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."religion", NEW."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_a2f87 ON "people_db_person";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_a2f87
    AFTER INSERT
    ON "people_db_person"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_a2f87();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_a2f87 ON "people_db_person" IS '87cc57eec7b2a022104a125ce90016ce8a297815';
;
--
-- Create trigger custom_snapshot_update on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_d7eeb()
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
            OLD."name_middle", OLD."name_suffix", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."religion", OLD."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_d7eeb ON "people_db_person";
CREATE TRIGGER pgtrigger_custom_snapshot_update_d7eeb
    AFTER UPDATE
    ON "people_db_person"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_d7eeb();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_d7eeb ON "people_db_person" IS 'f64c2722b1b6b84e40c847ee68f0c5f290d828f5';
;
--
-- Create trigger custom_snapshot_insert on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_ff819()
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
    VALUES (NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_ff819 ON "people_db_person_race";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_ff819
    AFTER INSERT
    ON "people_db_person_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_ff819();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_ff819 ON "people_db_person_race" IS 'c246558e8f0f4758186085b9bdbba0b228a5aa70';
;
--
-- Create trigger custom_snapshot_update on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_f23b1()
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
    VALUES (OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_f23b1 ON "people_db_person_race";
CREATE TRIGGER pgtrigger_custom_snapshot_update_f23b1
    AFTER UPDATE
    ON "people_db_person_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_f23b1();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_f23b1 ON "people_db_person_race" IS 'dc6d7cff394c39f23ab5748732192205b205435a';
;
--
-- Create trigger custom_snapshot_insert on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_4b44c()
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
    VALUES (NEW."date_created", NEW."date_end", NEW."date_granularity_end", NEW."date_granularity_start",
            NEW."date_modified", NEW."date_start", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id", NEW."political_party", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_4b44c ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_4b44c
    AFTER INSERT
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_4b44c();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_4b44c ON "people_db_politicalaffiliation" IS '20707e0a41339fac7d7f5b75941bb3ce429df57e';
;
--
-- Create trigger custom_snapshot_update on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_7a681()
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
            'custom_snapshot', OLD."id", OLD."political_party", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_7a681 ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_7a681
    AFTER UPDATE
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_7a681();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_7a681 ON "people_db_politicalaffiliation" IS '2a369734f26cc65434d34c6cd56546a3231c58bc';
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_6ac34()
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
    VALUES (NEW."appointer_id", NEW."court_id", NEW."date_confirmation", NEW."date_created", NEW."date_elected",
            NEW."date_granularity_start", NEW."date_granularity_termination", NEW."date_hearing",
            NEW."date_judicial_committee_action", NEW."date_modified", NEW."date_nominated",
            NEW."date_recess_appointment", NEW."date_referred_to_judicial_committee", NEW."date_retirement",
            NEW."date_start", NEW."date_termination", NEW."has_inferred_values", NEW."how_selected", NEW."id",
            NEW."job_title", NEW."judicial_committee_action", NEW."location_city", NEW."location_state",
            NEW."nomination_process", NEW."organization_name", NEW."person_id", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id", NEW."position_type", NEW."predecessor_id", NEW."school_id", NEW."sector",
            NEW."supervisor_id", NEW."termination_reason", NEW."voice_vote", NEW."vote_type", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_6ac34 ON "people_db_position";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_6ac34
    AFTER INSERT
    ON "people_db_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_6ac34();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_6ac34 ON "people_db_position" IS 'a2ccec1d66f76eb2b5ddb6ad059db063af54e02f';
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_3a9c5()
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
            'custom_snapshot', OLD."id", OLD."position_type", OLD."predecessor_id", OLD."school_id", OLD."sector",
            OLD."supervisor_id", OLD."termination_reason", OLD."voice_vote", OLD."vote_type", OLD."votes_no",
            OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_3a9c5 ON "people_db_position";
CREATE TRIGGER pgtrigger_custom_snapshot_update_3a9c5
    AFTER UPDATE
    ON "people_db_position"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_3a9c5();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_3a9c5 ON "people_db_position" IS '8ad093f982e96973a0413d1187e91e3872f59f50';
;
--
-- Create trigger custom_snapshot_insert on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_adc4f()
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
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_adc4f ON "people_db_race";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_adc4f
    AFTER INSERT
    ON "people_db_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_adc4f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_adc4f ON "people_db_race" IS '6bcf9e2e97d967385bc5ae354da41d3a790e0ce7';
;
--
-- Create trigger custom_snapshot_update on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_d01a8()
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
    VALUES (OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_d01a8 ON "people_db_race";
CREATE TRIGGER pgtrigger_custom_snapshot_update_d01a8
    AFTER UPDATE
    ON "people_db_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_d01a8();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_d01a8 ON "people_db_race" IS '3bfda2f7fdcb02cae529637b6bedd8e18b4eca71';
;
--
-- Create trigger custom_snapshot_insert on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_d427f()
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
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_retention", NEW."id", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id", NEW."position_id", NEW."retention_type", NEW."unopposed", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent", NEW."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_d427f ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_d427f
    AFTER INSERT
    ON "people_db_retentionevent"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_d427f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_d427f ON "people_db_retentionevent" IS '0c8d95edbd92ebc2c5900dcb6469f8fe32e52ea8';
;
--
-- Create trigger custom_snapshot_update on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_03dc7()
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
            'custom_snapshot', OLD."id", OLD."position_id", OLD."retention_type", OLD."unopposed", OLD."votes_no",
            OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent", OLD."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_03dc7 ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_custom_snapshot_update_03dc7
    AFTER UPDATE
    ON "people_db_retentionevent"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_03dc7();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_03dc7 ON "people_db_retentionevent" IS 'cd8dbf2a9ee6ba1607861e4791837ef0d1017da5';
;
--
-- Create trigger custom_snapshot_insert on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_e52c8()
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
    VALUES (NEW."date_created", NEW."date_modified", NEW."ein", NEW."id", NEW."is_alias_of_id", NEW."name",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_e52c8 ON "people_db_school";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_e52c8
    AFTER INSERT
    ON "people_db_school"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_e52c8();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_e52c8 ON "people_db_school" IS '42b7db4f73659ad07df6bffa15a6717c2d6412e8';
;
--
-- Create trigger custom_snapshot_update on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_e952c()
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
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_e952c ON "people_db_school";
CREATE TRIGGER pgtrigger_custom_snapshot_update_e952c
    AFTER UPDATE
    ON "people_db_school"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_e952c();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_e952c ON "people_db_school" IS 'b795b1e5123174e02e2cff69b8f6cd8ed6648651';
;
--
-- Create trigger custom_snapshot_insert on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_6d93b()
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
    VALUES (NEW."date_accessed", NEW."date_created", NEW."date_modified", NEW."id", NEW."notes", NEW."person_id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_6d93b ON "people_db_source";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_6d93b
    AFTER INSERT
    ON "people_db_source"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_6d93b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_6d93b ON "people_db_source" IS 'c38d7b29d0bb0cbc4f3cab0c9f6ed4322cdfb2bd';
;
--
-- Create trigger custom_snapshot_update on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_f797d()
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
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_f797d ON "people_db_source";
CREATE TRIGGER pgtrigger_custom_snapshot_update_f797d
    AFTER UPDATE
    ON "people_db_source"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_f797d();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_f797d ON "people_db_source" IS 'e097406278df3ca743df140d05c90afdad047dd4';
;
COMMIT;
