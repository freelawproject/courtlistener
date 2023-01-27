BEGIN;
--
-- Create model ABARatingEvent
--
CREATE TABLE "people_db_abaratingevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "year_rated"     smallint                 NULL CHECK ("year_rated" >= 0),
    "rating"         varchar(5)               NOT NULL
);
--
-- Create model EducationEvent
--
CREATE TABLE "people_db_educationevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "degree_level"   varchar(4)               NOT NULL,
    "degree_detail"  varchar(100)             NOT NULL,
    "degree_year"    smallint                 NULL CHECK ("degree_year" >= 0)
);
--
-- Create model PersonEvent
--
CREATE TABLE "people_db_personevent"
(
    "pgh_id"               serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"       timestamp with time zone NOT NULL,
    "pgh_label"            text                     NOT NULL,
    "id"                   integer                  NOT NULL,
    "date_created"         timestamp with time zone NOT NULL,
    "date_modified"        timestamp with time zone NOT NULL,
    "date_completed"       timestamp with time zone NULL,
    "fjc_id"               integer                  NULL,
    "slug"                 varchar(158)             NOT NULL,
    "name_first"           varchar(50)              NOT NULL,
    "name_middle"          varchar(50)              NOT NULL,
    "name_last"            varchar(50)              NOT NULL,
    "name_suffix"          varchar(5)               NOT NULL,
    "date_dob"             date                     NULL,
    "date_granularity_dob" varchar(15)              NOT NULL,
    "date_dod"             date                     NULL,
    "date_granularity_dod" varchar(15)              NOT NULL,
    "dob_city"             varchar(50)              NOT NULL,
    "dob_state"            varchar(2)               NOT NULL,
    "dob_country"          varchar(50)              NOT NULL,
    "dod_city"             varchar(50)              NOT NULL,
    "dod_state"            varchar(2)               NOT NULL,
    "dod_country"          varchar(50)              NOT NULL,
    "gender"               varchar(2)               NOT NULL,
    "religion"             varchar(30)              NOT NULL,
    "ftm_total_received"   double precision         NULL,
    "ftm_eid"              varchar(30)              NULL,
    "has_photo"            boolean                  NOT NULL
);
--
-- Create model PersonRaceEvent
--
CREATE TABLE "people_db_personraceevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model PoliticalAffiliationEvent
--
CREATE TABLE "people_db_politicalaffiliationevent"
(
    "pgh_id"                 serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"         timestamp with time zone NOT NULL,
    "pgh_label"              text                     NOT NULL,
    "id"                     integer                  NOT NULL,
    "date_created"           timestamp with time zone NOT NULL,
    "date_modified"          timestamp with time zone NOT NULL,
    "political_party"        varchar(5)               NOT NULL,
    "source"                 varchar(5)               NOT NULL,
    "date_start"             date                     NULL,
    "date_granularity_start" varchar(15)              NOT NULL,
    "date_end"               date                     NULL,
    "date_granularity_end"   varchar(15)              NOT NULL
);
--
-- Create model PositionEvent
--
CREATE TABLE "people_db_positionevent"
(
    "pgh_id"                              serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"                      timestamp with time zone NOT NULL,
    "pgh_label"                           text                     NOT NULL,
    "id"                                  integer                  NOT NULL,
    "date_created"                        timestamp with time zone NOT NULL,
    "date_modified"                       timestamp with time zone NOT NULL,
    "position_type"                       varchar(20)              NULL,
    "job_title"                           varchar(100)             NOT NULL,
    "sector"                              smallint                 NULL,
    "organization_name"                   varchar(120)             NULL,
    "location_city"                       varchar(50)              NOT NULL,
    "location_state"                      varchar(2)               NOT NULL,
    "date_nominated"                      date                     NULL,
    "date_elected"                        date                     NULL,
    "date_recess_appointment"             date                     NULL,
    "date_referred_to_judicial_committee" date                     NULL,
    "date_judicial_committee_action"      date                     NULL,
    "judicial_committee_action"           varchar(20)              NOT NULL,
    "date_hearing"                        date                     NULL,
    "date_confirmation"                   date                     NULL,
    "date_start"                          date                     NULL,
    "date_granularity_start"              varchar(15)              NOT NULL,
    "date_termination"                    date                     NULL,
    "termination_reason"                  varchar(25)              NOT NULL,
    "date_granularity_termination"        varchar(15)              NOT NULL,
    "date_retirement"                     date                     NULL,
    "nomination_process"                  varchar(20)              NOT NULL,
    "vote_type"                           varchar(2)               NOT NULL,
    "voice_vote"                          boolean                  NULL,
    "votes_yes"                           integer                  NULL CHECK ("votes_yes" >= 0),
    "votes_no"                            integer                  NULL CHECK ("votes_no" >= 0),
    "votes_yes_percent"                   double precision         NULL,
    "votes_no_percent"                    double precision         NULL,
    "how_selected"                        varchar(20)              NOT NULL,
    "has_inferred_values"                 boolean                  NOT NULL
);
--
-- Create model RaceEvent
--
CREATE TABLE "people_db_raceevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "race"           varchar(5)               NOT NULL
);
--
-- Create model RetentionEventEvent
--
CREATE TABLE "people_db_retentioneventevent"
(
    "pgh_id"            serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"    timestamp with time zone NOT NULL,
    "pgh_label"         text                     NOT NULL,
    "id"                integer                  NOT NULL,
    "date_created"      timestamp with time zone NOT NULL,
    "date_modified"     timestamp with time zone NOT NULL,
    "retention_type"    varchar(10)              NOT NULL,
    "date_retention"    date                     NOT NULL,
    "votes_yes"         integer                  NULL CHECK ("votes_yes" >= 0),
    "votes_no"          integer                  NULL CHECK ("votes_no" >= 0),
    "votes_yes_percent" double precision         NULL,
    "votes_no_percent"  double precision         NULL,
    "unopposed"         boolean                  NULL,
    "won"               boolean                  NULL
);
--
-- Create model SchoolEvent
--
CREATE TABLE "people_db_schoolevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "name"           varchar(120)             NOT NULL,
    "ein"            integer                  NULL
);
--
-- Create model SourceEvent
--
CREATE TABLE "people_db_sourceevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "url"            varchar(2000)            NOT NULL,
    "date_accessed"  date                     NULL,
    "notes"          text                     NOT NULL
);
--
-- Create proxy model PersonRace
--
--
-- Create trigger snapshot_insert on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_26a9a()
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
    INSERT INTO "people_db_abaratingevent" ("date_created", "date_modified", "id",
                                            "person_id", "pgh_context_id",
                                            "pgh_created_at", "pgh_label", "pgh_obj_id",
                                            "rating", "year_rated")
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."rating",
            NEW."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_26a9a ON "people_db_abarating";
CREATE TRIGGER pgtrigger_snapshot_insert_26a9a
    AFTER INSERT
    ON "people_db_abarating"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_26a9a();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_26a9a ON "people_db_abarating" IS '38afbd91cac2db46932d6d07aaed7d9803567549';
;
--
-- Create trigger snapshot_update on model abarating
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_1a35c()
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
    INSERT INTO "people_db_abaratingevent" ("date_created", "date_modified", "id",
                                            "person_id", "pgh_context_id",
                                            "pgh_created_at", "pgh_label", "pgh_obj_id",
                                            "rating", "year_rated")
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."rating",
            NEW."year_rated");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1a35c ON "people_db_abarating";
CREATE TRIGGER pgtrigger_snapshot_update_1a35c
    AFTER UPDATE
    ON "people_db_abarating"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_1a35c();

COMMENT ON TRIGGER pgtrigger_snapshot_update_1a35c ON "people_db_abarating" IS 'e0e91c8cc51f3f412a9971507acd01a7d5d90f6c';
;
--
-- Create trigger snapshot_insert on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_3f5b7()
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
    INSERT INTO "people_db_educationevent" ("date_created", "date_modified",
                                            "degree_detail", "degree_level",
                                            "degree_year", "id", "person_id",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id", "school_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."degree_detail",
            NEW."degree_level", NEW."degree_year", NEW."id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3f5b7 ON "people_db_education";
CREATE TRIGGER pgtrigger_snapshot_insert_3f5b7
    AFTER INSERT
    ON "people_db_education"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_3f5b7();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_3f5b7 ON "people_db_education" IS '6e3022272457672198047ac63eb5d671f1160900';
;
--
-- Create trigger snapshot_update on model education
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_342ab()
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
    INSERT INTO "people_db_educationevent" ("date_created", "date_modified",
                                            "degree_detail", "degree_level",
                                            "degree_year", "id", "person_id",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id", "school_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."degree_detail",
            NEW."degree_level", NEW."degree_year", NEW."id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."school_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_342ab ON "people_db_education";
CREATE TRIGGER pgtrigger_snapshot_update_342ab
    AFTER UPDATE
    ON "people_db_education"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_342ab();

COMMENT ON TRIGGER pgtrigger_snapshot_update_342ab ON "people_db_education" IS '22f1584d1eec3549d15b0715d2057512982bfce1';
;
--
-- Create trigger snapshot_insert on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_271f6()
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
    INSERT INTO "people_db_personevent" ("date_completed", "date_created", "date_dob",
                                         "date_dod", "date_granularity_dob",
                                         "date_granularity_dod", "date_modified",
                                         "dob_city", "dob_country", "dob_state",
                                         "dod_city", "dod_country", "dod_state",
                                         "fjc_id", "ftm_eid", "ftm_total_received",
                                         "gender", "has_photo", "id", "is_alias_of_id",
                                         "name_first", "name_last", "name_middle",
                                         "name_suffix", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id",
                                         "religion", "slug")
    VALUES (NEW."date_completed", NEW."date_created", NEW."date_dob", NEW."date_dod",
            NEW."date_granularity_dob", NEW."date_granularity_dod", NEW."date_modified",
            NEW."dob_city", NEW."dob_country", NEW."dob_state", NEW."dod_city",
            NEW."dod_country", NEW."dod_state", NEW."fjc_id", NEW."ftm_eid",
            NEW."ftm_total_received", NEW."gender", NEW."has_photo", NEW."id",
            NEW."is_alias_of_id", NEW."name_first", NEW."name_last", NEW."name_middle",
            NEW."name_suffix", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."religion", NEW."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_271f6 ON "people_db_person";
CREATE TRIGGER pgtrigger_snapshot_insert_271f6
    AFTER INSERT
    ON "people_db_person"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_271f6();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_271f6 ON "people_db_person" IS '3399a8b70fe203fa4328293647e4cb5d8d046c02';
;
--
-- Create trigger snapshot_update on model person
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_11bc7()
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
    INSERT INTO "people_db_personevent" ("date_completed", "date_created", "date_dob",
                                         "date_dod", "date_granularity_dob",
                                         "date_granularity_dod", "date_modified",
                                         "dob_city", "dob_country", "dob_state",
                                         "dod_city", "dod_country", "dod_state",
                                         "fjc_id", "ftm_eid", "ftm_total_received",
                                         "gender", "has_photo", "id", "is_alias_of_id",
                                         "name_first", "name_last", "name_middle",
                                         "name_suffix", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id",
                                         "religion", "slug")
    VALUES (NEW."date_completed", NEW."date_created", NEW."date_dob", NEW."date_dod",
            NEW."date_granularity_dob", NEW."date_granularity_dod", NEW."date_modified",
            NEW."dob_city", NEW."dob_country", NEW."dob_state", NEW."dod_city",
            NEW."dod_country", NEW."dod_state", NEW."fjc_id", NEW."ftm_eid",
            NEW."ftm_total_received", NEW."gender", NEW."has_photo", NEW."id",
            NEW."is_alias_of_id", NEW."name_first", NEW."name_last", NEW."name_middle",
            NEW."name_suffix", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."religion", NEW."slug");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_11bc7 ON "people_db_person";
CREATE TRIGGER pgtrigger_snapshot_update_11bc7
    AFTER UPDATE
    ON "people_db_person"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_11bc7();

COMMENT ON TRIGGER pgtrigger_snapshot_update_11bc7 ON "people_db_person" IS 'b1bb72d9f029f496b7d0ee3d0f3b04cda0901f15';
;
--
-- Create trigger snapshot_insert on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_ab32e()
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
    INSERT INTO "people_db_politicalaffiliationevent" ("date_created", "date_end",
                                                       "date_granularity_end",
                                                       "date_granularity_start",
                                                       "date_modified", "date_start",
                                                       "id", "person_id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "pgh_obj_id", "political_party",
                                                       "source")
    VALUES (NEW."date_created", NEW."date_end", NEW."date_granularity_end",
            NEW."date_granularity_start", NEW."date_modified", NEW."date_start",
            NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."political_party", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_ab32e ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_snapshot_insert_ab32e
    AFTER INSERT
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_ab32e();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_ab32e ON "people_db_politicalaffiliation" IS '2040550f71235de89f74925766dad68f0d993ff9';
;
--
-- Create trigger snapshot_update on model politicalaffiliation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6f60c()
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
    INSERT INTO "people_db_politicalaffiliationevent" ("date_created", "date_end",
                                                       "date_granularity_end",
                                                       "date_granularity_start",
                                                       "date_modified", "date_start",
                                                       "id", "person_id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "pgh_obj_id", "political_party",
                                                       "source")
    VALUES (NEW."date_created", NEW."date_end", NEW."date_granularity_end",
            NEW."date_granularity_start", NEW."date_modified", NEW."date_start",
            NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."political_party", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6f60c ON "people_db_politicalaffiliation";
CREATE TRIGGER pgtrigger_snapshot_update_6f60c
    AFTER UPDATE
    ON "people_db_politicalaffiliation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_6f60c();

COMMENT ON TRIGGER pgtrigger_snapshot_update_6f60c ON "people_db_politicalaffiliation" IS 'b8cabbf2261daf14201773211bf8a8ed006795a0';
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b594d()
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
    INSERT INTO "people_db_positionevent" ("appointer_id", "court_id",
                                           "date_confirmation", "date_created",
                                           "date_elected", "date_granularity_start",
                                           "date_granularity_termination",
                                           "date_hearing",
                                           "date_judicial_committee_action",
                                           "date_modified", "date_nominated",
                                           "date_recess_appointment",
                                           "date_referred_to_judicial_committee",
                                           "date_retirement", "date_start",
                                           "date_termination", "has_inferred_values",
                                           "how_selected", "id", "job_title",
                                           "judicial_committee_action", "location_city",
                                           "location_state", "nomination_process",
                                           "organization_name", "person_id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id", "position_type",
                                           "predecessor_id", "school_id", "sector",
                                           "supervisor_id", "termination_reason",
                                           "voice_vote", "vote_type", "votes_no",
                                           "votes_no_percent", "votes_yes",
                                           "votes_yes_percent")
    VALUES (NEW."appointer_id", NEW."court_id", NEW."date_confirmation",
            NEW."date_created", NEW."date_elected", NEW."date_granularity_start",
            NEW."date_granularity_termination", NEW."date_hearing",
            NEW."date_judicial_committee_action", NEW."date_modified",
            NEW."date_nominated", NEW."date_recess_appointment",
            NEW."date_referred_to_judicial_committee", NEW."date_retirement",
            NEW."date_start", NEW."date_termination", NEW."has_inferred_values",
            NEW."how_selected", NEW."id", NEW."job_title",
            NEW."judicial_committee_action", NEW."location_city", NEW."location_state",
            NEW."nomination_process", NEW."organization_name", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position_type",
            NEW."predecessor_id", NEW."school_id", NEW."sector", NEW."supervisor_id",
            NEW."termination_reason", NEW."voice_vote", NEW."vote_type", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b594d ON "people_db_position";
CREATE TRIGGER pgtrigger_snapshot_insert_b594d
    AFTER INSERT
    ON "people_db_position"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_b594d();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_b594d ON "people_db_position" IS '1d52228d6e0ab49de5953ffaf0f2f0675a5f05fb';
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_d5203()
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
    INSERT INTO "people_db_positionevent" ("appointer_id", "court_id",
                                           "date_confirmation", "date_created",
                                           "date_elected", "date_granularity_start",
                                           "date_granularity_termination",
                                           "date_hearing",
                                           "date_judicial_committee_action",
                                           "date_modified", "date_nominated",
                                           "date_recess_appointment",
                                           "date_referred_to_judicial_committee",
                                           "date_retirement", "date_start",
                                           "date_termination", "has_inferred_values",
                                           "how_selected", "id", "job_title",
                                           "judicial_committee_action", "location_city",
                                           "location_state", "nomination_process",
                                           "organization_name", "person_id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id", "position_type",
                                           "predecessor_id", "school_id", "sector",
                                           "supervisor_id", "termination_reason",
                                           "voice_vote", "vote_type", "votes_no",
                                           "votes_no_percent", "votes_yes",
                                           "votes_yes_percent")
    VALUES (NEW."appointer_id", NEW."court_id", NEW."date_confirmation",
            NEW."date_created", NEW."date_elected", NEW."date_granularity_start",
            NEW."date_granularity_termination", NEW."date_hearing",
            NEW."date_judicial_committee_action", NEW."date_modified",
            NEW."date_nominated", NEW."date_recess_appointment",
            NEW."date_referred_to_judicial_committee", NEW."date_retirement",
            NEW."date_start", NEW."date_termination", NEW."has_inferred_values",
            NEW."how_selected", NEW."id", NEW."job_title",
            NEW."judicial_committee_action", NEW."location_city", NEW."location_state",
            NEW."nomination_process", NEW."organization_name", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position_type",
            NEW."predecessor_id", NEW."school_id", NEW."sector", NEW."supervisor_id",
            NEW."termination_reason", NEW."voice_vote", NEW."vote_type", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d5203 ON "people_db_position";
CREATE TRIGGER pgtrigger_snapshot_update_d5203
    AFTER UPDATE
    ON "people_db_position"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_d5203();

COMMENT ON TRIGGER pgtrigger_snapshot_update_d5203 ON "people_db_position" IS 'f62cbd62f81f9750b2bea507e2949ce0a489178b';
;
--
-- Create trigger snapshot_insert on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_36b13()
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
    INSERT INTO "people_db_raceevent" ("id", "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id", "race")
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_36b13 ON "people_db_race";
CREATE TRIGGER pgtrigger_snapshot_insert_36b13
    AFTER INSERT
    ON "people_db_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_36b13();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_36b13 ON "people_db_race" IS '8a4663070ba5ff0667cc164dd946060fab9ba608';
;
--
-- Create trigger snapshot_update on model race
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_901ca()
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
    INSERT INTO "people_db_raceevent" ("id", "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id", "race")
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."race");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_901ca ON "people_db_race";
CREATE TRIGGER pgtrigger_snapshot_update_901ca
    AFTER UPDATE
    ON "people_db_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_901ca();

COMMENT ON TRIGGER pgtrigger_snapshot_update_901ca ON "people_db_race" IS '0bf94b32fec5e43b310d4fae1921b08c69b36372';
;
--
-- Create trigger snapshot_insert on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_123d1()
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
    INSERT INTO "people_db_retentioneventevent" ("date_created", "date_modified",
                                                 "date_retention", "id",
                                                 "pgh_context_id", "pgh_created_at",
                                                 "pgh_label", "pgh_obj_id",
                                                 "position_id", "retention_type",
                                                 "unopposed", "votes_no",
                                                 "votes_no_percent", "votes_yes",
                                                 "votes_yes_percent", "won")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_retention", NEW."id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position_id",
            NEW."retention_type", NEW."unopposed", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent",
            NEW."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_123d1 ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_snapshot_insert_123d1
    AFTER INSERT
    ON "people_db_retentionevent"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_123d1();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_123d1 ON "people_db_retentionevent" IS 'a6db6bcc5bb0336b5e82cf88d19cc2f51a766ea9';
;
--
-- Create trigger snapshot_update on model retentionevent
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_21cad()
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
    INSERT INTO "people_db_retentioneventevent" ("date_created", "date_modified",
                                                 "date_retention", "id",
                                                 "pgh_context_id", "pgh_created_at",
                                                 "pgh_label", "pgh_obj_id",
                                                 "position_id", "retention_type",
                                                 "unopposed", "votes_no",
                                                 "votes_no_percent", "votes_yes",
                                                 "votes_yes_percent", "won")
    VALUES (NEW."date_created", NEW."date_modified", NEW."date_retention", NEW."id",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position_id",
            NEW."retention_type", NEW."unopposed", NEW."votes_no",
            NEW."votes_no_percent", NEW."votes_yes", NEW."votes_yes_percent",
            NEW."won");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_21cad ON "people_db_retentionevent";
CREATE TRIGGER pgtrigger_snapshot_update_21cad
    AFTER UPDATE
    ON "people_db_retentionevent"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_21cad();

COMMENT ON TRIGGER pgtrigger_snapshot_update_21cad ON "people_db_retentionevent" IS 'e2438569e360c33bc29399e1305e06d439594cc2';
;
--
-- Create trigger snapshot_insert on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_79a6c()
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
    INSERT INTO "people_db_schoolevent" ("date_created", "date_modified", "ein", "id",
                                         "is_alias_of_id", "name", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."ein", NEW."id",
            NEW."is_alias_of_id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_79a6c ON "people_db_school";
CREATE TRIGGER pgtrigger_snapshot_insert_79a6c
    AFTER INSERT
    ON "people_db_school"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_79a6c();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_79a6c ON "people_db_school" IS 'a426fb7533491b4154a1b497916f19beb621fdca';
;
--
-- Create trigger snapshot_update on model school
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_d61c7()
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
    INSERT INTO "people_db_schoolevent" ("date_created", "date_modified", "ein", "id",
                                         "is_alias_of_id", "name", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."ein", NEW."id",
            NEW."is_alias_of_id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d61c7 ON "people_db_school";
CREATE TRIGGER pgtrigger_snapshot_update_d61c7
    AFTER UPDATE
    ON "people_db_school"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_d61c7();

COMMENT ON TRIGGER pgtrigger_snapshot_update_d61c7 ON "people_db_school" IS '3259b91d858cdd9473b46427c388f7a082570ad9';
;
--
-- Create trigger snapshot_insert on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_c86e5()
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
    INSERT INTO "people_db_sourceevent" ("date_accessed", "date_created",
                                         "date_modified", "id", "notes", "person_id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "url")
    VALUES (NEW."date_accessed", NEW."date_created", NEW."date_modified", NEW."id",
            NEW."notes", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c86e5 ON "people_db_source";
CREATE TRIGGER pgtrigger_snapshot_insert_c86e5
    AFTER INSERT
    ON "people_db_source"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_c86e5();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_c86e5 ON "people_db_source" IS 'dce08f4538b1598dee760074979b61e3e08056b5';
;
--
-- Create trigger snapshot_update on model source
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6b08f()
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
    INSERT INTO "people_db_sourceevent" ("date_accessed", "date_created",
                                         "date_modified", "id", "notes", "person_id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id", "url")
    VALUES (NEW."date_accessed", NEW."date_created", NEW."date_modified", NEW."id",
            NEW."notes", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6b08f ON "people_db_source";
CREATE TRIGGER pgtrigger_snapshot_update_6b08f
    AFTER UPDATE
    ON "people_db_source"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_6b08f();

COMMENT ON TRIGGER pgtrigger_snapshot_update_6b08f ON "people_db_source" IS 'f8a4312c845687e821d9f82dbf72c52e833433b1';
;
--
-- Add field person to sourceevent
--
ALTER TABLE "people_db_sourceevent"
    ADD COLUMN "person_id" integer NULL;
--
-- Add field pgh_context to sourceevent
--
ALTER TABLE "people_db_sourceevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to sourceevent
--
ALTER TABLE "people_db_sourceevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field is_alias_of to schoolevent
--
ALTER TABLE "people_db_schoolevent"
    ADD COLUMN "is_alias_of_id" integer NULL;
--
-- Add field pgh_context to schoolevent
--
ALTER TABLE "people_db_schoolevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to schoolevent
--
ALTER TABLE "people_db_schoolevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field pgh_context to retentioneventevent
--
ALTER TABLE "people_db_retentioneventevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to retentioneventevent
--
ALTER TABLE "people_db_retentioneventevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field position to retentioneventevent
--
ALTER TABLE "people_db_retentioneventevent"
    ADD COLUMN "position_id" integer NULL;
--
-- Add field pgh_context to raceevent
--
ALTER TABLE "people_db_raceevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to raceevent
--
ALTER TABLE "people_db_raceevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field appointer to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "appointer_id" integer NULL;
--
-- Add field court to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "court_id" varchar(15) NULL;
--
-- Add field person to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "person_id" integer NULL;
--
-- Add field pgh_context to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field predecessor to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "predecessor_id" integer NULL;
--
-- Add field school to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "school_id" integer NULL;
--
-- Add field supervisor to positionevent
--
ALTER TABLE "people_db_positionevent"
    ADD COLUMN "supervisor_id" integer NULL;
--
-- Add field person to politicalaffiliationevent
--
ALTER TABLE "people_db_politicalaffiliationevent"
    ADD COLUMN "person_id" integer NULL;
--
-- Add field pgh_context to politicalaffiliationevent
--
ALTER TABLE "people_db_politicalaffiliationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to politicalaffiliationevent
--
ALTER TABLE "people_db_politicalaffiliationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field person to personraceevent
--
ALTER TABLE "people_db_personraceevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to personraceevent
--
ALTER TABLE "people_db_personraceevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field race to personraceevent
--
ALTER TABLE "people_db_personraceevent"
    ADD COLUMN "race_id" integer NOT NULL;
--
-- Add field is_alias_of to personevent
--
ALTER TABLE "people_db_personevent"
    ADD COLUMN "is_alias_of_id" integer NULL;
--
-- Add field pgh_context to personevent
--
ALTER TABLE "people_db_personevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to personevent
--
ALTER TABLE "people_db_personevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field person to educationevent
--
ALTER TABLE "people_db_educationevent"
    ADD COLUMN "person_id" integer NULL;
--
-- Add field pgh_context to educationevent
--
ALTER TABLE "people_db_educationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to educationevent
--
ALTER TABLE "people_db_educationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field school to educationevent
--
ALTER TABLE "people_db_educationevent"
    ADD COLUMN "school_id" integer NOT NULL;
--
-- Add field person to abaratingevent
--
ALTER TABLE "people_db_abaratingevent"
    ADD COLUMN "person_id" integer NULL;
--
-- Add field pgh_context to abaratingevent
--
ALTER TABLE "people_db_abaratingevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to abaratingevent
--
ALTER TABLE "people_db_abaratingevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Create trigger snapshot_insert on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_3bcce()
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
    INSERT INTO "people_db_personraceevent" ("id", "person_id", "pgh_context_id",
                                             "pgh_created_at", "pgh_label", "race_id")
    VALUES (NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3bcce ON "people_db_person_race";
CREATE TRIGGER pgtrigger_snapshot_insert_3bcce
    AFTER INSERT
    ON "people_db_person_race"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_3bcce();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_3bcce ON "people_db_person_race" IS 'b416d0145735d42c05a78c8340e3fc58f97791a1';
;
--
-- Create trigger snapshot_update on model personrace
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_134c2()
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
    INSERT INTO "people_db_personraceevent" ("id", "person_id", "pgh_context_id",
                                             "pgh_created_at", "pgh_label", "race_id")
    VALUES (NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."race_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_134c2 ON "people_db_person_race";
CREATE TRIGGER pgtrigger_snapshot_update_134c2
    AFTER UPDATE
    ON "people_db_person_race"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_134c2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_134c2 ON "people_db_person_race" IS '496584b9aebfd67b12c361533769f1833e376511';
;
CREATE INDEX "people_db_sourceevent_person_id_f32cf8b3" ON "people_db_sourceevent" ("person_id");
CREATE INDEX "people_db_sourceevent_pgh_context_id_6bf9fb8f" ON "people_db_sourceevent" ("pgh_context_id");
CREATE INDEX "people_db_sourceevent_pgh_obj_id_c37b1d95" ON "people_db_sourceevent" ("pgh_obj_id");
CREATE INDEX "people_db_schoolevent_is_alias_of_id_4c4332d7" ON "people_db_schoolevent" ("is_alias_of_id");
CREATE INDEX "people_db_schoolevent_pgh_context_id_b32512bd" ON "people_db_schoolevent" ("pgh_context_id");
CREATE INDEX "people_db_schoolevent_pgh_obj_id_57bf2a67" ON "people_db_schoolevent" ("pgh_obj_id");
CREATE INDEX "people_db_retentioneventevent_pgh_context_id_81f7850b" ON "people_db_retentioneventevent" ("pgh_context_id");
CREATE INDEX "people_db_retentioneventevent_pgh_obj_id_902d74ea" ON "people_db_retentioneventevent" ("pgh_obj_id");
CREATE INDEX "people_db_retentioneventevent_position_id_96c16566" ON "people_db_retentioneventevent" ("position_id");
CREATE INDEX "people_db_raceevent_pgh_context_id_590006cf" ON "people_db_raceevent" ("pgh_context_id");
CREATE INDEX "people_db_raceevent_pgh_obj_id_f7ec57e8" ON "people_db_raceevent" ("pgh_obj_id");
CREATE INDEX "people_db_positionevent_appointer_id_9a1a141d" ON "people_db_positionevent" ("appointer_id");
CREATE INDEX "people_db_positionevent_court_id_c27f27bf" ON "people_db_positionevent" ("court_id");
CREATE INDEX "people_db_positionevent_court_id_c27f27bf_like" ON "people_db_positionevent" ("court_id" varchar_pattern_ops);
CREATE INDEX "people_db_positionevent_person_id_b48e5d5c" ON "people_db_positionevent" ("person_id");
CREATE INDEX "people_db_positionevent_pgh_context_id_91818e04" ON "people_db_positionevent" ("pgh_context_id");
CREATE INDEX "people_db_positionevent_pgh_obj_id_e37b1a99" ON "people_db_positionevent" ("pgh_obj_id");
CREATE INDEX "people_db_positionevent_predecessor_id_a183a0e5" ON "people_db_positionevent" ("predecessor_id");
CREATE INDEX "people_db_positionevent_school_id_8435314e" ON "people_db_positionevent" ("school_id");
CREATE INDEX "people_db_positionevent_supervisor_id_d1b31dbb" ON "people_db_positionevent" ("supervisor_id");
CREATE INDEX "people_db_politicalaffiliationevent_person_id_968b07ce" ON "people_db_politicalaffiliationevent" ("person_id");
CREATE INDEX "people_db_politicalaffiliationevent_pgh_context_id_dfbcdb75" ON "people_db_politicalaffiliationevent" ("pgh_context_id");
CREATE INDEX "people_db_politicalaffiliationevent_pgh_obj_id_c98e3cf6" ON "people_db_politicalaffiliationevent" ("pgh_obj_id");
CREATE INDEX "people_db_personraceevent_person_id_000fffe6" ON "people_db_personraceevent" ("person_id");
CREATE INDEX "people_db_personraceevent_pgh_context_id_6e61479f" ON "people_db_personraceevent" ("pgh_context_id");
CREATE INDEX "people_db_personraceevent_race_id_ec19c576" ON "people_db_personraceevent" ("race_id");
CREATE INDEX "people_db_personevent_is_alias_of_id_dff0de5e" ON "people_db_personevent" ("is_alias_of_id");
CREATE INDEX "people_db_personevent_pgh_context_id_8c18edc2" ON "people_db_personevent" ("pgh_context_id");
CREATE INDEX "people_db_personevent_pgh_obj_id_3a44721c" ON "people_db_personevent" ("pgh_obj_id");
CREATE INDEX "people_db_educationevent_person_id_86892be3" ON "people_db_educationevent" ("person_id");
CREATE INDEX "people_db_educationevent_pgh_context_id_93dac561" ON "people_db_educationevent" ("pgh_context_id");
CREATE INDEX "people_db_educationevent_pgh_obj_id_242c5dea" ON "people_db_educationevent" ("pgh_obj_id");
CREATE INDEX "people_db_educationevent_school_id_5d83b038" ON "people_db_educationevent" ("school_id");
CREATE INDEX "people_db_abaratingevent_person_id_976485e8" ON "people_db_abaratingevent" ("person_id");
CREATE INDEX "people_db_abaratingevent_pgh_context_id_60d3496a" ON "people_db_abaratingevent" ("pgh_context_id");
CREATE INDEX "people_db_abaratingevent_pgh_obj_id_0e6a9bc3" ON "people_db_abaratingevent" ("pgh_obj_id");
COMMIT;
