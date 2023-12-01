BEGIN;
--
-- Remove trigger snapshot_insert from model dockettag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_d9def ON "favorites_dockettag";
--
-- Remove trigger snapshot_update from model dockettag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2cb4a ON "favorites_dockettag";
--
-- Remove trigger snapshot_insert from model note
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_7e480 ON "favorites_note";
--
-- Remove trigger snapshot_update from model note
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc74c ON "favorites_note";
--
-- Remove trigger snapshot_insert from model prayer
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_9becd ON "favorites_prayer";
--
-- Remove trigger snapshot_update from model prayer
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f75d ON "favorites_prayer";
--
-- Remove trigger snapshot_insert from model usertag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_38cf8 ON "favorites_usertag";
--
-- Remove trigger snapshot_update from model usertag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8ec9c ON "favorites_usertag";
--
-- Create trigger update_or_delete_snapshot_update on model dockettag
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_88501()
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
    INSERT INTO "favorites_dockettagevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                            "pgh_obj_id", "tag_id")
    VALUES (OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_88501 ON "favorites_dockettag";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_88501
    AFTER UPDATE
    ON "favorites_dockettag"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_88501();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_88501 ON "favorites_dockettag" IS '8f1df53f9cd8f17eb461118f6b48459fbf9db58e';
;
--
-- Create trigger update_or_delete_snapshot_delete on model dockettag
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_1a570()
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
    INSERT INTO "favorites_dockettagevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                            "pgh_obj_id", "tag_id")
    VALUES (OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_1a570 ON "favorites_dockettag";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_1a570
    AFTER DELETE
    ON "favorites_dockettag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_1a570();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_1a570 ON "favorites_dockettag" IS 'be481286dac59ff8609039001c4d5c0079f533c7';
;
--
-- Create trigger update_or_delete_snapshot_update on model note
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_ed3a1()
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
    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "date_created", "date_modified", "docket_id_id",
                                       "id", "name", "notes", "pgh_context_id", "pgh_created_at", "pgh_label",
                                       "pgh_obj_id", "recap_doc_id_id", "user_id")
    VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id",
            OLD."id", OLD."name", OLD."notes", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."recap_doc_id_id", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ed3a1 ON "favorites_note";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_ed3a1
    AFTER UPDATE
    ON "favorites_note"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."cluster_id_id" IS DISTINCT FROM NEW."cluster_id_id" OR
          OLD."audio_id_id" IS DISTINCT FROM NEW."audio_id_id" OR
          OLD."docket_id_id" IS DISTINCT FROM NEW."docket_id_id" OR
          OLD."recap_doc_id_id" IS DISTINCT FROM NEW."recap_doc_id_id" OR OLD."name" IS DISTINCT FROM NEW."name" OR
          OLD."notes" IS DISTINCT FROM NEW."notes")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_ed3a1();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_ed3a1 ON "favorites_note" IS 'fcd6d536ae66f06cea145de113f778913b839c34';
;
--
-- Create trigger update_or_delete_snapshot_delete on model note
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_b6726()
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
    INSERT INTO "favorites_noteevent" ("audio_id_id", "cluster_id_id", "date_created", "date_modified", "docket_id_id",
                                       "id", "name", "notes", "pgh_context_id", "pgh_created_at", "pgh_label",
                                       "pgh_obj_id", "recap_doc_id_id", "user_id")
    VALUES (OLD."audio_id_id", OLD."cluster_id_id", OLD."date_created", OLD."date_modified", OLD."docket_id_id",
            OLD."id", OLD."name", OLD."notes", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."recap_doc_id_id", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_b6726 ON "favorites_note";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_b6726
    AFTER DELETE
    ON "favorites_note"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_b6726();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_b6726 ON "favorites_note" IS '4c1d04b7683ae122c2497aeee499ec9ac1025f4a';
;
--
-- Create trigger update_or_delete_snapshot_update on model prayer
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_67cd0()
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
    INSERT INTO "favorites_prayerevent" ("date_created", "id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                         "pgh_obj_id", "recap_document_id", "status", "user_id")
    VALUES (OLD."date_created", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."recap_document_id", OLD."status", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_67cd0 ON "favorites_prayer";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_67cd0
    AFTER UPDATE
    ON "favorites_prayer"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_67cd0();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_67cd0 ON "favorites_prayer" IS '3bc4cc39bc791dfeb8fff181e29662e13ceae902';
;
--
-- Create trigger update_or_delete_snapshot_delete on model prayer
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_89611()
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
    INSERT INTO "favorites_prayerevent" ("date_created", "id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                         "pgh_obj_id", "recap_document_id", "status", "user_id")
    VALUES (OLD."date_created", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."recap_document_id", OLD."status", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_89611 ON "favorites_prayer";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_89611
    AFTER DELETE
    ON "favorites_prayer"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_89611();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_89611 ON "favorites_prayer" IS 'e37fb648af3bce037c4d52a45d4202357da1ca8c';
;
--
-- Create trigger update_or_delete_snapshot_update on model usertag
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_9deec()
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
    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified", "description", "id", "name",
                                          "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "published",
                                          "title", "user_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id", OLD."published", OLD."title", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_9deec ON "favorites_usertag";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_9deec
    AFTER UPDATE
    ON "favorites_usertag"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."user_id" IS DISTINCT FROM NEW."user_id" OR OLD."name" IS DISTINCT FROM NEW."name" OR
          OLD."title" IS DISTINCT FROM NEW."title" OR OLD."description" IS DISTINCT FROM NEW."description" OR
          OLD."published" IS DISTINCT FROM NEW."published")
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_9deec();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_9deec ON "favorites_usertag" IS '1f0b6589dbf1673b54b022f55026d469b7497e06';
;
--
-- Create trigger update_or_delete_snapshot_delete on model usertag
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_e4ac4()
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
    INSERT INTO "favorites_usertagevent" ("date_created", "date_modified", "description", "id", "name",
                                          "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "published",
                                          "title", "user_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."description", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id", OLD."published", OLD."title", OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_e4ac4 ON "favorites_usertag";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_e4ac4
    AFTER DELETE
    ON "favorites_usertag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_e4ac4();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_e4ac4 ON "favorites_usertag" IS 'ae91cd3be4454f2f23f7e656d244f63d8d79ff18';
;
COMMIT;
