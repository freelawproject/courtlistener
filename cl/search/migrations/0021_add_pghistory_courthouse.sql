BEGIN;
--
-- Create model CourtAppealsToEvent
--
CREATE TABLE "search_courtappealstoevent"
(
    "pgh_id"         integer                  NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model CourthouseEvent
--
CREATE TABLE "search_courthouseevent"
(
    "pgh_id"         integer                  NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "court_seat"     boolean                  NULL,
    "building_name"  text                     NOT NULL,
    "address1"       text                     NOT NULL,
    "address2"       text                     NOT NULL,
    "city"           text                     NOT NULL,
    "county"         text                     NOT NULL,
    "state"          varchar(2)               NOT NULL,
    "zip_code"       varchar(10)              NOT NULL,
    "country_code"   text                     NOT NULL
);
--
-- Create proxy model CourtAppealsTo
--
-- (no-op)
--
-- Create trigger update_or_delete_snapshot_update on model courthouse
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_e394a()
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
    INSERT INTO "search_courthouseevent" ("address1", "address2", "building_name",
                                          "city", "country_code", "county", "court_id",
                                          "court_seat", "id", "pgh_context_id",
                                          "pgh_created_at", "pgh_label", "pgh_obj_id",
                                          "state", "zip_code")
    VALUES (OLD."address1", OLD."address2", OLD."building_name", OLD."city",
            OLD."country_code", OLD."county", OLD."court_id", OLD."court_seat",
            OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."state", OLD."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_e394a ON "search_courthouse";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_e394a
    AFTER UPDATE
    ON "search_courthouse"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_e394a();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_e394a ON "search_courthouse" IS 'b3a38d787937fd3591951860f2bf9fc980f8f87f';

--
-- Create trigger update_or_delete_snapshot_delete on model courthouse
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_aabf8()
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
    INSERT INTO "search_courthouseevent" ("address1", "address2", "building_name",
                                          "city", "country_code", "county", "court_id",
                                          "court_seat", "id", "pgh_context_id",
                                          "pgh_created_at", "pgh_label", "pgh_obj_id",
                                          "state", "zip_code")
    VALUES (OLD."address1", OLD."address2", OLD."building_name", OLD."city",
            OLD."country_code", OLD."county", OLD."court_id", OLD."court_seat",
            OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id", OLD."state", OLD."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_aabf8 ON "search_courthouse";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_aabf8
    AFTER DELETE
    ON "search_courthouse"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_aabf8();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_aabf8 ON "search_courthouse" IS '52ca038a3b52ba39ca02facbb87977a5cd1f59a3';

--
-- Add field court to courthouseevent
--
ALTER TABLE "search_courthouseevent"
    ADD COLUMN "court_id" varchar(15) NOT NULL;
--
-- Add field pgh_context to courthouseevent
--
ALTER TABLE "search_courthouseevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to courthouseevent
--
ALTER TABLE "search_courthouseevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field from_court to courtappealstoevent
--
ALTER TABLE "search_courtappealstoevent"
    ADD COLUMN "from_court_id" varchar(15) NOT NULL;
--
-- Add field pgh_context to courtappealstoevent
--
ALTER TABLE "search_courtappealstoevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field to_court to courtappealstoevent
--
ALTER TABLE "search_courtappealstoevent"
    ADD COLUMN "to_court_id" varchar(15) NOT NULL;
--
-- Create trigger update_or_delete_snapshot_update on model courtappealsto
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_cc38c()
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
    INSERT INTO "search_courtappealstoevent" ("from_court_id", "id", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "to_court_id")
    VALUES (OLD."from_court_id", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."to_court_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_cc38c ON "search_court_appeals_to";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_cc38c
    AFTER UPDATE
    ON "search_court_appeals_to"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_cc38c();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_cc38c ON "search_court_appeals_to" IS '5224e4a3e58a56dba44b76077e4915f981134af3';

--
-- Create trigger update_or_delete_snapshot_delete on model courtappealsto
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_01d31()
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
    INSERT INTO "search_courtappealstoevent" ("from_court_id", "id", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "to_court_id")
    VALUES (OLD."from_court_id", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."to_court_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_01d31 ON "search_court_appeals_to";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_01d31
    AFTER DELETE
    ON "search_court_appeals_to"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_01d31();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_01d31 ON "search_court_appeals_to" IS '60c71e3e490f9be107654bc74bf4149d448b4842';

CREATE INDEX "search_courthouseevent_court_id_ecdd5b8a" ON "search_courthouseevent" ("court_id");
CREATE INDEX "search_courthouseevent_court_id_ecdd5b8a_like" ON "search_courthouseevent" ("court_id" varchar_pattern_ops);
CREATE INDEX "search_courthouseevent_pgh_context_id_affccfe3" ON "search_courthouseevent" ("pgh_context_id");
CREATE INDEX "search_courthouseevent_pgh_obj_id_2bdd6824" ON "search_courthouseevent" ("pgh_obj_id");
CREATE INDEX "search_courtappealstoevent_from_court_id_75784b8f" ON "search_courtappealstoevent" ("from_court_id");
CREATE INDEX "search_courtappealstoevent_from_court_id_75784b8f_like" ON "search_courtappealstoevent" ("from_court_id" varchar_pattern_ops);
CREATE INDEX "search_courtappealstoevent_pgh_context_id_e65511b3" ON "search_courtappealstoevent" ("pgh_context_id");
CREATE INDEX "search_courtappealstoevent_to_court_id_5540ee1b" ON "search_courtappealstoevent" ("to_court_id");
CREATE INDEX "search_courtappealstoevent_to_court_id_5540ee1b_like" ON "search_courtappealstoevent" ("to_court_id" varchar_pattern_ops);
COMMIT;
