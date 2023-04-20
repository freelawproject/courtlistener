BEGIN;
--
-- Remove trigger snapshot_insert from model grouppermissions
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_47043 ON "auth_group_permissions";
--
-- Remove trigger snapshot_update from model grouppermissions
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8e426 ON "auth_group_permissions";
--
-- Remove trigger snapshot_insert from model groupproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0bb2c ON "auth_group";
--
-- Remove trigger snapshot_update from model groupproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1e0d3 ON "auth_group";
--
-- Remove trigger snapshot_insert from model permissionproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c294b ON "auth_permission";
--
-- Remove trigger snapshot_update from model permissionproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f943 ON "auth_permission";
--
-- Remove trigger snapshot_insert from model usergroups
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cb58e ON "auth_user_groups";
--
-- Remove trigger snapshot_update from model usergroups
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_591a4 ON "auth_user_groups";
--
-- Remove trigger snapshot_insert from model userpermissions
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_46522 ON "auth_user_user_permissions";
--
-- Remove trigger snapshot_update from model userpermissions
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_80307 ON "auth_user_user_permissions";
--
-- Remove trigger snapshot_insert from model userprofile
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_31610 ON "users_userprofile";
--
-- Remove trigger snapshot_update from model userprofile
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_74231 ON "users_userprofile";
--
-- Remove trigger snapshot_insert from model userprofilebarmembership
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_de1c8 ON "users_userprofile_barmembership";
--
-- Remove trigger snapshot_update from model userprofilebarmembership
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cb3f2 ON "users_userprofile_barmembership";
--
-- Remove trigger snapshot_insert from model userproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_70025 ON "auth_user";
--
-- Remove trigger snapshot_update from model userproxy
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_b6e18 ON "auth_user";
--
-- Create trigger update_or_delete_snapshot_update on model grouppermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_7bfc9()
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
    INSERT INTO "users_grouppermissionsevent" ("group_id", "id", "permission_id", "pgh_context_id",
                                               "pgh_created_at", "pgh_label")
    VALUES (OLD."group_id", OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_7bfc9 ON "auth_group_permissions";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_7bfc9
    AFTER UPDATE
    ON "auth_group_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_7bfc9();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_7bfc9 ON "auth_group_permissions" IS 'dda10f45a908286aee8498dd6919f4469ce9b9ad';
;
--
-- Create trigger update_or_delete_snapshot_delete on model grouppermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_09233()
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
    INSERT INTO "users_grouppermissionsevent" ("group_id", "id", "permission_id", "pgh_context_id",
                                               "pgh_created_at", "pgh_label")
    VALUES (OLD."group_id", OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_09233 ON "auth_group_permissions";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_09233
    AFTER DELETE
    ON "auth_group_permissions"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_09233();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_09233 ON "auth_group_permissions" IS '4402ea2dbb97b3274b2af5623b8744983805172c';
;
--
-- Create trigger update_or_delete_snapshot_update on model groupproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_98718()
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
    INSERT INTO "users_groupproxyevent" ("id", "name", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id")
    VALUES (OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_98718 ON "auth_group";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_98718
    AFTER UPDATE
    ON "auth_group"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_98718();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_98718 ON "auth_group" IS 'aa1d93825a6d36ca10f98b47e436f8c817f6842e';
;
--
-- Create trigger update_or_delete_snapshot_delete on model groupproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_4d24b()
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
    INSERT INTO "users_groupproxyevent" ("id", "name", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "pgh_obj_id")
    VALUES (OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_4d24b ON "auth_group";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_4d24b
    AFTER DELETE
    ON "auth_group"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_4d24b();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_4d24b ON "auth_group" IS '9dd3dc558d20bb42c358636e9620377cc2369c2c';
;
--
-- Create trigger update_or_delete_snapshot_update on model permissionproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_e1c9f()
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
    INSERT INTO "users_permissionproxyevent" ("codename", "content_type_id", "id", "name",
                                              "pgh_context_id", "pgh_created_at", "pgh_label",
                                              "pgh_obj_id")
    VALUES (OLD."codename", OLD."content_type_id", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_e1c9f ON "auth_permission";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_e1c9f
    AFTER UPDATE
    ON "auth_permission"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_e1c9f();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_e1c9f ON "auth_permission" IS '14a3f3cafcfbdd3842550ed7e8020d54045d611e';
;
--
-- Create trigger update_or_delete_snapshot_delete on model permissionproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_11509()
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
    INSERT INTO "users_permissionproxyevent" ("codename", "content_type_id", "id", "name",
                                              "pgh_context_id", "pgh_created_at", "pgh_label",
                                              "pgh_obj_id")
    VALUES (OLD."codename", OLD."content_type_id", OLD."id", OLD."name", _pgh_attach_context(),
            NOW(), 'update_or_delete_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_11509 ON "auth_permission";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_11509
    AFTER DELETE
    ON "auth_permission"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_11509();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_11509 ON "auth_permission" IS 'e04e12d446b8e9a74882a42f972fe9010770b419';
;
--
-- Create trigger update_or_delete_snapshot_update on model usergroups
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_58112()
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
    INSERT INTO "users_usergroupsevent" ("group_id", "id", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "user_id")
    VALUES (OLD."group_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_58112 ON "auth_user_groups";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_58112
    AFTER UPDATE
    ON "auth_user_groups"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_58112();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_58112 ON "auth_user_groups" IS '81e6f6fc164efc85f6edcc0ee1d49805b172ef5e';
;
--
-- Create trigger update_or_delete_snapshot_delete on model usergroups
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_cd0a6()
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
    INSERT INTO "users_usergroupsevent" ("group_id", "id", "pgh_context_id", "pgh_created_at",
                                         "pgh_label", "user_id")
    VALUES (OLD."group_id", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot',
            OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_cd0a6 ON "auth_user_groups";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_cd0a6
    AFTER DELETE
    ON "auth_user_groups"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_cd0a6();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_cd0a6 ON "auth_user_groups" IS '04d987731772f8f175f3dc7dfa3506ae9d4c3894';
;
--
-- Create trigger update_or_delete_snapshot_update on model userpermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_b7585()
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
    INSERT INTO "users_userpermissionsevent" ("id", "permission_id", "pgh_context_id",
                                              "pgh_created_at", "pgh_label", "user_id")
    VALUES (OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_b7585 ON "auth_user_user_permissions";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_b7585
    AFTER UPDATE
    ON "auth_user_user_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_b7585();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_b7585 ON "auth_user_user_permissions" IS '0e8867ca245b7b4a4350b540f6a611ebf05ddbc7';
;
--
-- Create trigger update_or_delete_snapshot_delete on model userpermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_17cec()
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
    INSERT INTO "users_userpermissionsevent" ("id", "permission_id", "pgh_context_id",
                                              "pgh_created_at", "pgh_label", "user_id")
    VALUES (OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_17cec ON "auth_user_user_permissions";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_17cec
    AFTER DELETE
    ON "auth_user_user_permissions"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_17cec();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_17cec ON "auth_user_user_permissions" IS '0aeeaceeb8547987202afae4fabe968e44040a2d';
;
--
-- Create trigger update_or_delete_snapshot_update on model userprofile
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_c9b7b()
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
    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2",
                                          "auto_subscribe", "avatar", "city",
                                          "docket_default_order_desc", "email_confirmed",
                                          "employer", "id", "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at", "pgh_label",
                                          "pgh_obj_id", "plaintext_preferred", "recap_email",
                                          "state", "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (OLD."activation_key", OLD."address1", OLD."address2", OLD."auto_subscribe",
            OLD."avatar", OLD."city", OLD."docket_default_order_desc", OLD."email_confirmed",
            OLD."employer", OLD."id", OLD."is_tester", OLD."key_expires", OLD."notes",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."plaintext_preferred", OLD."recap_email", OLD."state", OLD."stub_account",
            OLD."unlimited_docket_alerts", OLD."user_id", OLD."wants_newsletter", OLD."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_c9b7b ON "users_userprofile";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_c9b7b
    AFTER UPDATE
    ON "users_userprofile"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_c9b7b();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_c9b7b ON "users_userprofile" IS '0dde39ef7888bd8ac1239a2f665b33b8de703af4';
;
--
-- Create trigger update_or_delete_snapshot_delete on model userprofile
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_f463b()
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
    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2",
                                          "auto_subscribe", "avatar", "city",
                                          "docket_default_order_desc", "email_confirmed",
                                          "employer", "id", "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at", "pgh_label",
                                          "pgh_obj_id", "plaintext_preferred", "recap_email",
                                          "state", "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (OLD."activation_key", OLD."address1", OLD."address2", OLD."auto_subscribe",
            OLD."avatar", OLD."city", OLD."docket_default_order_desc", OLD."email_confirmed",
            OLD."employer", OLD."id", OLD."is_tester", OLD."key_expires", OLD."notes",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id",
            OLD."plaintext_preferred", OLD."recap_email", OLD."state", OLD."stub_account",
            OLD."unlimited_docket_alerts", OLD."user_id", OLD."wants_newsletter", OLD."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_f463b ON "users_userprofile";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_f463b
    AFTER DELETE
    ON "users_userprofile"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_f463b();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_f463b ON "users_userprofile" IS 'f3a89f21d5285009b1c78a6e6434dc51da5b9314';
;
--
-- Create trigger update_or_delete_snapshot_update on model userprofilebarmembership
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_dd24a()
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
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id", "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (OLD."barmembership_id", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_dd24a ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_dd24a
    AFTER UPDATE
    ON "users_userprofile_barmembership"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_dd24a();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_dd24a ON "users_userprofile_barmembership" IS '40454d33f14945213a91ef7401ab0d32abcb69ea';
;
--
-- Create trigger update_or_delete_snapshot_delete on model userprofilebarmembership
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_1a7fe()
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
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id", "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (OLD."barmembership_id", OLD."id", _pgh_attach_context(), NOW(),
            'update_or_delete_snapshot', OLD."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_1a7fe ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_1a7fe
    AFTER DELETE
    ON "users_userprofile_barmembership"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_1a7fe();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_1a7fe ON "users_userprofile_barmembership" IS '112520df9e7eede66b40cdcc23ae23175ce42362';
;
--
-- Create trigger update_or_delete_snapshot_update on model userproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_d8df2()
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
    INSERT INTO "users_userproxyevent" ("date_joined", "email", "first_name", "id", "is_active",
                                        "is_staff", "is_superuser", "last_login", "last_name",
                                        "password", "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "username")
    VALUES (OLD."date_joined", OLD."email", OLD."first_name", OLD."id", OLD."is_active",
            OLD."is_staff", OLD."is_superuser", OLD."last_login", OLD."last_name", OLD."password",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."username");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_d8df2 ON "auth_user";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_update_d8df2
    AFTER UPDATE
    ON "auth_user"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_d8df2();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_d8df2 ON "auth_user" IS '39a450a930c2a34ee6ce8f0523e6e1e53c3fdcfd';
;
--
-- Create trigger update_or_delete_snapshot_delete on model userproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_9691d()
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
    INSERT INTO "users_userproxyevent" ("date_joined", "email", "first_name", "id", "is_active",
                                        "is_staff", "is_superuser", "last_login", "last_name",
                                        "password", "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "username")
    VALUES (OLD."date_joined", OLD."email", OLD."first_name", OLD."id", OLD."is_active",
            OLD."is_staff", OLD."is_superuser", OLD."last_login", OLD."last_name", OLD."password",
            _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."username");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_9691d ON "auth_user";
CREATE TRIGGER pgtrigger_update_or_delete_snapshot_delete_9691d
    AFTER DELETE
    ON "auth_user"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_9691d();

COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_9691d ON "auth_user" IS '5fc996933c46fa65e83c44b0f81b514f074ceeb2';
;
COMMIT;
