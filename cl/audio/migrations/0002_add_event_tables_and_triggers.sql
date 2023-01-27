BEGIN;
--
-- Create model AudioEvent
--
CREATE TABLE "audio_audioevent"
(
    "pgh_id"                   serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"           timestamp with time zone NOT NULL,
    "pgh_label"                text                     NOT NULL,
    "id"                       integer                  NOT NULL,
    "date_created"             timestamp with time zone NOT NULL,
    "date_modified"            timestamp with time zone NOT NULL,
    "source"                   varchar(10)              NOT NULL,
    "case_name_short"          text                     NOT NULL,
    "case_name"                text                     NOT NULL,
    "case_name_full"           text                     NOT NULL,
    "judges"                   text                     NULL,
    "sha1"                     varchar(40)              NOT NULL,
    "download_url"             varchar(500)             NULL,
    "local_path_mp3"           varchar(100)             NOT NULL,
    "local_path_original_file" varchar(100)             NOT NULL,
    "filepath_ia"              varchar(1000)            NOT NULL,
    "ia_upload_failure_count"  smallint                 NULL,
    "duration"                 smallint                 NULL,
    "processing_complete"      boolean                  NOT NULL,
    "date_blocked"             date                     NULL,
    "blocked"                  boolean                  NOT NULL,
    "stt_status"               smallint                 NOT NULL,
    "stt_google_response"      text                     NOT NULL
);
--
-- Create model AudioPanelEvent
--
CREATE TABLE "audio_audiopanelevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create proxy model AudioPanel
--
--
-- Create trigger snapshot_insert on model audio
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_43674()
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
    INSERT INTO "audio_audioevent" ("blocked", "case_name", "case_name_full",
                                    "case_name_short", "date_blocked", "date_created",
                                    "date_modified", "docket_id", "download_url",
                                    "duration", "filepath_ia",
                                    "ia_upload_failure_count", "id", "judges",
                                    "local_path_mp3", "local_path_original_file",
                                    "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "processing_complete", "sha1",
                                    "source", "stt_google_response", "stt_status")
    VALUES (NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short",
            NEW."date_blocked", NEW."date_created", NEW."date_modified",
            NEW."docket_id", NEW."download_url", NEW."duration", NEW."filepath_ia",
            NEW."ia_upload_failure_count", NEW."id", NEW."judges", NEW."local_path_mp3",
            NEW."local_path_original_file", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."processing_complete", NEW."sha1", NEW."source",
            NEW."stt_google_response", NEW."stt_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_43674 ON "audio_audio";
CREATE TRIGGER pgtrigger_snapshot_insert_43674
    AFTER INSERT
    ON "audio_audio"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_43674();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_43674 ON "audio_audio" IS '5fb8248949cbe5b6e4330bc7503bdfdbe7bd2d14';
;
--
-- Create trigger snapshot_update on model audio
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_c0234()
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
    INSERT INTO "audio_audioevent" ("blocked", "case_name", "case_name_full",
                                    "case_name_short", "date_blocked", "date_created",
                                    "date_modified", "docket_id", "download_url",
                                    "duration", "filepath_ia",
                                    "ia_upload_failure_count", "id", "judges",
                                    "local_path_mp3", "local_path_original_file",
                                    "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "processing_complete", "sha1",
                                    "source", "stt_google_response", "stt_status")
    VALUES (NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short",
            NEW."date_blocked", NEW."date_created", NEW."date_modified",
            NEW."docket_id", NEW."download_url", NEW."duration", NEW."filepath_ia",
            NEW."ia_upload_failure_count", NEW."id", NEW."judges", NEW."local_path_mp3",
            NEW."local_path_original_file", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."processing_complete", NEW."sha1", NEW."source",
            NEW."stt_google_response", NEW."stt_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_c0234 ON "audio_audio";
CREATE TRIGGER pgtrigger_snapshot_update_c0234
    AFTER UPDATE
    ON "audio_audio"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_c0234();

COMMENT ON TRIGGER pgtrigger_snapshot_update_c0234 ON "audio_audio" IS 'de7e7fe34af4612d2d3e775f3c57bbc5b7fdebb7';
;
--
-- Add field audio to audiopanelevent
--
ALTER TABLE "audio_audiopanelevent"
    ADD COLUMN "audio_id" integer NOT NULL;
--
-- Add field person to audiopanelevent
--
ALTER TABLE "audio_audiopanelevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to audiopanelevent
--
ALTER TABLE "audio_audiopanelevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field docket to audioevent
--
ALTER TABLE "audio_audioevent"
    ADD COLUMN "docket_id" integer NULL;
--
-- Add field pgh_context to audioevent
--
ALTER TABLE "audio_audioevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to audioevent
--
ALTER TABLE "audio_audioevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Create trigger snapshot_insert on model audiopanel
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_0141b()
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
    INSERT INTO "audio_audiopanelevent" ("audio_id", "id", "person_id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label")
    VALUES (NEW."audio_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(),
            'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0141b ON "audio_audio_panel";
CREATE TRIGGER pgtrigger_snapshot_insert_0141b
    AFTER INSERT
    ON "audio_audio_panel"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_0141b();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_0141b ON "audio_audio_panel" IS 'e069d7d8bfc5654b553214f657719fa0772a8e4d';
;
--
-- Create trigger snapshot_update on model audiopanel
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_17291()
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
    INSERT INTO "audio_audiopanelevent" ("audio_id", "id", "person_id",
                                         "pgh_context_id", "pgh_created_at",
                                         "pgh_label")
    VALUES (NEW."audio_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(),
            'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_17291 ON "audio_audio_panel";
CREATE TRIGGER pgtrigger_snapshot_update_17291
    AFTER UPDATE
    ON "audio_audio_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_17291();

COMMENT ON TRIGGER pgtrigger_snapshot_update_17291 ON "audio_audio_panel" IS '515a9726c66bdf5232725f4a4a00761cafbbc7af';
;
CREATE INDEX "audio_audiopanelevent_audio_id_3aab9feb" ON "audio_audiopanelevent" ("audio_id");
CREATE INDEX "audio_audiopanelevent_person_id_0280e6c8" ON "audio_audiopanelevent" ("person_id");
CREATE INDEX "audio_audiopanelevent_pgh_context_id_5c5401fc" ON "audio_audiopanelevent" ("pgh_context_id");
CREATE INDEX "audio_audioevent_docket_id_d4acad63" ON "audio_audioevent" ("docket_id");
CREATE INDEX "audio_audioevent_pgh_context_id_f695da7c" ON "audio_audioevent" ("pgh_context_id");
CREATE INDEX "audio_audioevent_pgh_obj_id_d4cc0c20" ON "audio_audioevent" ("pgh_obj_id");
COMMIT;
