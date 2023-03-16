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
-- Create trigger custom_snapshot_update on model grouppermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_9dcb9()
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
    INSERT INTO "users_grouppermissionsevent" ("group_id", "id", "permission_id", "pgh_context_id", "pgh_created_at",
                                               "pgh_label")
    VALUES (OLD."group_id", OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_9dcb9 ON "auth_group_permissions";
CREATE TRIGGER pgtrigger_custom_snapshot_update_9dcb9
    AFTER UPDATE
    ON "auth_group_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_9dcb9();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_9dcb9 ON "auth_group_permissions" IS '1a8e56395d1425a8b0fb5014d274dc76d74a110e';
;
--
-- Create trigger custom_snapshot_update on model groupproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_3afa4()
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
    INSERT INTO "users_groupproxyevent" ("id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (OLD."id", OLD."name", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_3afa4 ON "auth_group";
CREATE TRIGGER pgtrigger_custom_snapshot_update_3afa4
    AFTER UPDATE
    ON "auth_group"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_3afa4();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_3afa4 ON "auth_group" IS 'ba78b5f0795b51cf67736067a943b3fecc3af9f0';
;
--
-- Create trigger custom_snapshot_update on model permissionproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_6176f()
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
    INSERT INTO "users_permissionproxyevent" ("codename", "content_type_id", "id", "name", "pgh_context_id",
                                              "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (OLD."codename", OLD."content_type_id", OLD."id", OLD."name", _pgh_attach_context(), NOW(),
            'custom_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_6176f ON "auth_permission";
CREATE TRIGGER pgtrigger_custom_snapshot_update_6176f
    AFTER UPDATE
    ON "auth_permission"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_6176f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_6176f ON "auth_permission" IS '81dd17f9a5fe251ed7fb28dbe0e6e4d91a07ffdb';
;
--
-- Create trigger custom_snapshot_update on model usergroups
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_cfd8c()
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
    INSERT INTO "users_usergroupsevent" ("group_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "user_id")
    VALUES (OLD."group_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_cfd8c ON "auth_user_groups";
CREATE TRIGGER pgtrigger_custom_snapshot_update_cfd8c
    AFTER UPDATE
    ON "auth_user_groups"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_cfd8c();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_cfd8c ON "auth_user_groups" IS 'ceba1d0a6dcdd784efa76bab3ae8e352a3893b44';
;
--
-- Create trigger custom_snapshot_update on model userpermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_f1f22()
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
    INSERT INTO "users_userpermissionsevent" ("id", "permission_id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                              "user_id")
    VALUES (OLD."id", OLD."permission_id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_f1f22 ON "auth_user_user_permissions";
CREATE TRIGGER pgtrigger_custom_snapshot_update_f1f22
    AFTER UPDATE
    ON "auth_user_user_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_f1f22();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_f1f22 ON "auth_user_user_permissions" IS '38242fce23b92a51e16d445a2a71739afd67c3e3';
;
--
-- Create trigger custom_snapshot_update on model userprofile
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_34fb2()
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
    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city",
                                          "email_confirmed", "employer", "id", "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                          "plaintext_preferred", "recap_email", "state", "stub_account",
                                          "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code")
    VALUES (OLD."activation_key", OLD."address1", OLD."address2", OLD."auto_subscribe", OLD."avatar", OLD."city",
            OLD."email_confirmed", OLD."employer", OLD."id", OLD."is_tester", OLD."key_expires", OLD."notes",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."plaintext_preferred", OLD."recap_email",
            OLD."state", OLD."stub_account", OLD."unlimited_docket_alerts", OLD."user_id", OLD."wants_newsletter",
            OLD."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_34fb2 ON "users_userprofile";
CREATE TRIGGER pgtrigger_custom_snapshot_update_34fb2
    AFTER UPDATE
    ON "users_userprofile"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_34fb2();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_34fb2 ON "users_userprofile" IS '0d086b7148d56eb34bf1491e0b222d82d7e006a2';
;
--
-- Create trigger custom_snapshot_update on model userprofilebarmembership
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_d59ec()
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
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id", "pgh_context_id", "pgh_created_at",
                                                       "pgh_label", "userprofile_id")
    VALUES (OLD."barmembership_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_d59ec ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_custom_snapshot_update_d59ec
    AFTER UPDATE
    ON "users_userprofile_barmembership"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_d59ec();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_d59ec ON "users_userprofile_barmembership" IS '323ae60f4f3db7e65d3e75d54df24d227b8a274f';
;
--
-- Create trigger custom_snapshot_update on model userproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_aa503()
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
    INSERT INTO "users_userproxyevent" ("date_joined", "email", "first_name", "id", "is_active", "is_staff",
                                        "is_superuser", "last_login", "last_name", "password", "pgh_context_id",
                                        "pgh_created_at", "pgh_label", "pgh_obj_id", "username")
    VALUES (OLD."date_joined", OLD."email", OLD."first_name", OLD."id", OLD."is_active", OLD."is_staff",
            OLD."is_superuser", OLD."last_login", OLD."last_name", OLD."password", _pgh_attach_context(), NOW(),
            'custom_snapshot', OLD."id", OLD."username");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_aa503 ON "auth_user";
CREATE TRIGGER pgtrigger_custom_snapshot_update_aa503
    AFTER UPDATE
    ON "auth_user"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_aa503();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_aa503 ON "auth_user" IS '77562423dbf9160fc240cd27f477ae8a877b188b';
;
COMMIT;
