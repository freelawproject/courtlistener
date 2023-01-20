BEGIN;
--
-- Create model DocketTagEvent
--
CREATE TABLE "favorites_dockettagevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model NoteEvent
--
CREATE TABLE "favorites_noteevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NULL,
    "name"           varchar(100)             NOT NULL,
    "notes"          text                     NOT NULL
);
--
-- Create model PrayerEvent
--
CREATE TABLE "favorites_prayerevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "status"         smallint                 NOT NULL
);
--
-- Create model UserTagEvent
--
CREATE TABLE "favorites_usertagevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "name"           varchar(50)              NOT NULL,
    "title"          text                     NOT NULL,
    "description"    text                     NOT NULL,
    "published"      boolean                  NOT NULL
);
--
-- Create trigger snapshot_insert on model dockettag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_d9def()
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
    INSERT INTO "favorites_dockettagevent" ("docket_id", "id",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id",
                                            "tag_id")
    VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_d9def ON "favorites_dockettag";
CREATE TRIGGER pgtrigger_snapshot_insert_d9def
    AFTER INSERT
    ON "favorites_dockettag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_d9def();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_d9def ON "favorites_dockettag" IS '29317d5fa7f67f1673d3e8629f95ad1d4611680a';
;
--
-- Create trigger snapshot_update on model dockettag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_2cb4a()
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
    INSERT INTO "favorites_dockettagevent" ("docket_id", "id",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id",
                                            "tag_id")
    VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2cb4a ON "favorites_dockettag";
CREATE TRIGGER pgtrigger_snapshot_update_2cb4a
    AFTER UPDATE
    ON "favorites_dockettag"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_2cb4a();

COMMENT ON TRIGGER pgtrigger_snapshot_update_2cb4a ON "favorites_dockettag" IS '741d5f0b8e26c83cdc757b4924fbd3cc22a7ecfc';
;
--
-- Create trigger snapshot_insert on model note
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_7e480()
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
    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id",
                                       "date_created", "date_modified",
                                       "docket_id_id", "id", "name", "notes",
                                       "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id",
                                       "recap_doc_id_id", "user_id")
    VALUES (NEW."audio_id_id", NEW."cluster_id_id", NEW."date_created",
            NEW."date_modified", NEW."docket_id_id", NEW."id", NEW."name",
            NEW."notes", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."recap_doc_id_id", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_7e480 ON "favorites_note";
CREATE TRIGGER pgtrigger_snapshot_insert_7e480
    AFTER INSERT
    ON "favorites_note"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_7e480();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_7e480 ON "favorites_note" IS '3783aab50aab2ed0ac3eae8e6e6b70f2f72cef6a';
;
--
-- Create trigger snapshot_update on model note
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cc74c()
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
    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id",
                                       "date_created", "date_modified",
                                       "docket_id_id", "id", "name", "notes",
                                       "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id",
                                       "recap_doc_id_id", "user_id")
    VALUES (NEW."audio_id_id", NEW."cluster_id_id", NEW."date_created",
            NEW."date_modified", NEW."docket_id_id", NEW."id", NEW."name",
            NEW."notes", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."recap_doc_id_id", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc74c ON "favorites_note";
CREATE TRIGGER pgtrigger_snapshot_update_cc74c
    AFTER UPDATE
    ON "favorites_note"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cc74c();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cc74c ON "favorites_note" IS 'a8a09a17456f083920b6e36d8c7f6e2695aa0b4d';
;
--
-- Create trigger snapshot_insert on model prayer
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_9becd()
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
    INSERT INTO "favorites_prayerevent" ("date_created", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id",
                                         "recap_document_id", "status",
                                         "user_id")
    VALUES (NEW."date_created", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."recap_document_id", NEW."status",
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_9becd ON "favorites_prayer";
CREATE TRIGGER pgtrigger_snapshot_insert_9becd
    AFTER INSERT
    ON "favorites_prayer"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_9becd();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_9becd ON "favorites_prayer" IS '96821b8db3f57317a614f51f61d735a30970305e';
;
--
-- Create trigger snapshot_update on model prayer
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8f75d()
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
    INSERT INTO "favorites_prayerevent" ("date_created", "id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id",
                                         "recap_document_id", "status",
                                         "user_id")
    VALUES (NEW."date_created", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."recap_document_id", NEW."status",
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f75d ON "favorites_prayer";
CREATE TRIGGER pgtrigger_snapshot_update_8f75d
    AFTER UPDATE
    ON "favorites_prayer"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_8f75d();

COMMENT ON TRIGGER pgtrigger_snapshot_update_8f75d ON "favorites_prayer" IS '43216b61a7ffdd9308b5e6064efd9276d791b9ec';
;
--
-- Create trigger snapshot_insert on model usertag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_38cf8()
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
    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified",
                                          "description", "id", "name",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "published", "title", "user_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."published", NEW."title", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_38cf8 ON "favorites_usertag";
CREATE TRIGGER pgtrigger_snapshot_insert_38cf8
    AFTER INSERT
    ON "favorites_usertag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_38cf8();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_38cf8 ON "favorites_usertag" IS 'd24099cd7f1c3d33a6410d564e6ede52c12bec1e';
;
--
-- Create trigger snapshot_update on model usertag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8ec9c()
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
    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified",
                                          "description", "id", "name",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "published", "title", "user_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."description",
            NEW."id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."published", NEW."title", NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8ec9c ON "favorites_usertag";
CREATE TRIGGER pgtrigger_snapshot_update_8ec9c
    AFTER UPDATE
    ON "favorites_usertag"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR
          OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."date_modified" IS DISTINCT FROM NEW."date_modified" OR
          OLD."user_id" IS DISTINCT FROM NEW."user_id" OR
          OLD."name" IS DISTINCT FROM NEW."name" OR
          OLD."title" IS DISTINCT FROM NEW."title" OR
          OLD."description" IS DISTINCT FROM NEW."description" OR
          OLD."published" IS DISTINCT FROM NEW."published")
EXECUTE PROCEDURE pgtrigger_snapshot_update_8ec9c();

COMMENT ON TRIGGER pgtrigger_snapshot_update_8ec9c ON "favorites_usertag" IS '620a5e1618c400875c028db158d92e5c0bdd520d';
;
--
-- Add field pgh_context to usertagevent
--
ALTER TABLE "favorites_usertagevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to usertagevent
--
ALTER TABLE "favorites_usertagevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to usertagevent
--
ALTER TABLE "favorites_usertagevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field pgh_context to prayerevent
--
ALTER TABLE "favorites_prayerevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to prayerevent
--
ALTER TABLE "favorites_prayerevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field recap_document to prayerevent
--
ALTER TABLE "favorites_prayerevent"
    ADD COLUMN "recap_document_id" integer NOT NULL;
--
-- Add field user to prayerevent
--
ALTER TABLE "favorites_prayerevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field audio_id to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "audio_id_id" integer NULL;
--
-- Add field cluster_id to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "cluster_id_id" integer NULL;
--
-- Add field docket_id to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "docket_id_id" integer NULL;
--
-- Add field pgh_context to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field recap_doc_id to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "recap_doc_id_id" integer NULL;
--
-- Add field user to noteevent
--
ALTER TABLE "favorites_noteevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field docket to dockettagevent
--
ALTER TABLE "favorites_dockettagevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to dockettagevent
--
ALTER TABLE "favorites_dockettagevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to dockettagevent
--
ALTER TABLE "favorites_dockettagevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field tag to dockettagevent
--
ALTER TABLE "favorites_dockettagevent"
    ADD COLUMN "tag_id" integer NOT NULL;
CREATE INDEX "favorites_usertagevent_pgh_context_id_68ca3d8b" ON "favorites_usertagevent" ("pgh_context_id");
CREATE INDEX "favorites_usertagevent_pgh_obj_id_8fb8b8e0" ON "favorites_usertagevent" ("pgh_obj_id");
CREATE INDEX "favorites_usertagevent_user_id_b9deaf93" ON "favorites_usertagevent" ("user_id");
CREATE INDEX "favorites_prayerevent_pgh_context_id_68d05a9a" ON "favorites_prayerevent" ("pgh_context_id");
CREATE INDEX "favorites_prayerevent_pgh_obj_id_1d06bd82" ON "favorites_prayerevent" ("pgh_obj_id");
CREATE INDEX "favorites_prayerevent_recap_document_id_321dc692" ON "favorites_prayerevent" ("recap_document_id");
CREATE INDEX "favorites_prayerevent_user_id_323fda24" ON "favorites_prayerevent" ("user_id");
CREATE INDEX "favorites_noteevent_audio_id_id_4f51a817" ON "favorites_noteevent" ("audio_id_id");
CREATE INDEX "favorites_noteevent_cluster_id_id_b4f4489b" ON "favorites_noteevent" ("cluster_id_id");
CREATE INDEX "favorites_noteevent_docket_id_id_34e8a8d8" ON "favorites_noteevent" ("docket_id_id");
CREATE INDEX "favorites_noteevent_pgh_context_id_f35e9f7a" ON "favorites_noteevent" ("pgh_context_id");
CREATE INDEX "favorites_noteevent_pgh_obj_id_3a677483" ON "favorites_noteevent" ("pgh_obj_id");
CREATE INDEX "favorites_noteevent_recap_doc_id_id_13e40efc" ON "favorites_noteevent" ("recap_doc_id_id");
CREATE INDEX "favorites_noteevent_user_id_390cdd45" ON "favorites_noteevent" ("user_id");
CREATE INDEX "favorites_dockettagevent_docket_id_d568bfb0" ON "favorites_dockettagevent" ("docket_id");
CREATE INDEX "favorites_dockettagevent_pgh_context_id_65598797" ON "favorites_dockettagevent" ("pgh_context_id");
CREATE INDEX "favorites_dockettagevent_pgh_obj_id_b755bff7" ON "favorites_dockettagevent" ("pgh_obj_id");
CREATE INDEX "favorites_dockettagevent_tag_id_7e0b2f04" ON "favorites_dockettagevent" ("tag_id");
COMMIT;
