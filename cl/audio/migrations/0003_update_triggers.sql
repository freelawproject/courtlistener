BEGIN;
--
-- Remove trigger snapshot_insert from model audio
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_43674 ON "audio_audio";
--
-- Remove trigger snapshot_update from model audio
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_c0234 ON "audio_audio";
--
-- Remove trigger snapshot_insert from model audiopanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0141b ON "audio_audio_panel";
--
-- Remove trigger snapshot_update from model audiopanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_17291 ON "audio_audio_panel";
--
-- Create trigger custom_snapshot_insert on model audio
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_46b12()
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
    INSERT INTO "audio_audioevent" ("blocked", "case_name", "case_name_full", "case_name_short", "date_blocked",
                                    "date_created", "date_modified", "docket_id", "download_url", "duration",
                                    "filepath_ia", "ia_upload_failure_count", "id", "judges", "local_path_mp3",
                                    "local_path_original_file", "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "processing_complete", "sha1", "source", "stt_google_response",
                                    "stt_status")
    VALUES (NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short", NEW."date_blocked",
            NEW."date_created", NEW."date_modified", NEW."docket_id", NEW."download_url", NEW."duration",
            NEW."filepath_ia", NEW."ia_upload_failure_count", NEW."id", NEW."judges", NEW."local_path_mp3",
            NEW."local_path_original_file", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."processing_complete", NEW."sha1", NEW."source", NEW."stt_google_response", NEW."stt_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_46b12 ON "audio_audio";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_46b12
    AFTER INSERT
    ON "audio_audio"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_46b12();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_46b12 ON "audio_audio" IS 'bf2b5b180eff7217f098764f0db8a4788b0fe298';
;
--
-- Create trigger custom_snapshot_update on model audio
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_ad0df()
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
    INSERT INTO "audio_audioevent" ("blocked", "case_name", "case_name_full", "case_name_short", "date_blocked",
                                    "date_created", "date_modified", "docket_id", "download_url", "duration",
                                    "filepath_ia", "ia_upload_failure_count", "id", "judges", "local_path_mp3",
                                    "local_path_original_file", "pgh_context_id", "pgh_created_at", "pgh_label",
                                    "pgh_obj_id", "processing_complete", "sha1", "source", "stt_google_response",
                                    "stt_status")
    VALUES (OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short", OLD."date_blocked",
            OLD."date_created", OLD."date_modified", OLD."docket_id", OLD."download_url", OLD."duration",
            OLD."filepath_ia", OLD."ia_upload_failure_count", OLD."id", OLD."judges", OLD."local_path_mp3",
            OLD."local_path_original_file", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."processing_complete", OLD."sha1", OLD."source", OLD."stt_google_response", OLD."stt_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_ad0df ON "audio_audio";
CREATE TRIGGER pgtrigger_custom_snapshot_update_ad0df
    AFTER UPDATE
    ON "audio_audio"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_ad0df();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_ad0df ON "audio_audio" IS 'f99a4957a9d0c2f1e06ed878efdb04ad7e693506';
;
--
-- Create trigger custom_snapshot_insert on model audiopanel
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_ae584()
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
    INSERT INTO "audio_audiopanelevent" ("audio_id", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label")
    VALUES (NEW."audio_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_ae584 ON "audio_audio_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_ae584
    AFTER INSERT
    ON "audio_audio_panel"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_ae584();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_ae584 ON "audio_audio_panel" IS 'debf11c5c5b4eb8328954c96876754fa574d9082';
;
--
-- Create trigger custom_snapshot_update on model audiopanel
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_2497c()
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
    INSERT INTO "audio_audiopanelevent" ("audio_id", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label")
    VALUES (OLD."audio_id", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_2497c ON "audio_audio_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_update_2497c
    AFTER UPDATE
    ON "audio_audio_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2497c();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2497c ON "audio_audio_panel" IS '085b4ec0423661deb14f614162b05e76db4fa3da';
;
COMMIT;
