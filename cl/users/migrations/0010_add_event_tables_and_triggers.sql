BEGIN;
--
-- Create model GroupPermissionsEvent
--
CREATE TABLE "users_grouppermissionsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model GroupProxyEvent
--
CREATE TABLE "users_groupproxyevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "name"           varchar(150)             NOT NULL
);
--
-- Create model PermissionProxyEvent
--
CREATE TABLE "users_permissionproxyevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "name"           varchar(255)             NOT NULL,
    "codename"       varchar(100)             NOT NULL
);
--
-- Create model UserGroupsEvent
--
CREATE TABLE "users_usergroupsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model UserPermissionsEvent
--
CREATE TABLE "users_userpermissionsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model UserProfileBarMembershipEvent
--
CREATE TABLE "users_userprofilebarmembershipevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model UserProfileEvent
--
CREATE TABLE "users_userprofileevent"
(
    "pgh_id"                  serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"          timestamp with time zone NOT NULL,
    "pgh_label"               text                     NOT NULL,
    "id"                      integer                  NOT NULL,
    "stub_account"            boolean                  NOT NULL,
    "employer"                varchar(100)             NULL,
    "address1"                varchar(100)             NULL,
    "address2"                varchar(100)             NULL,
    "city"                    varchar(50)              NULL,
    "state"                   varchar(2)               NULL,
    "zip_code"                varchar(10)              NULL,
    "avatar"                  varchar(100)             NOT NULL,
    "wants_newsletter"        boolean                  NOT NULL,
    "unlimited_docket_alerts" boolean                  NOT NULL,
    "plaintext_preferred"     boolean                  NOT NULL,
    "activation_key"          varchar(40)              NOT NULL,
    "key_expires"             timestamp with time zone NULL,
    "email_confirmed"         boolean                  NOT NULL,
    "notes"                   text                     NOT NULL,
    "is_tester"               boolean                  NOT NULL,
    "recap_email"             varchar(254)             NOT NULL,
    "auto_subscribe"          boolean                  NOT NULL
);
--
-- Create model UserProxyEvent
--
CREATE TABLE "users_userproxyevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "password"       varchar(128)             NOT NULL,
    "last_login"     timestamp with time zone NULL,
    "is_superuser"   boolean                  NOT NULL,
    "username"       varchar(150)             NOT NULL,
    "first_name"     varchar(150)             NOT NULL,
    "last_name"      varchar(150)             NOT NULL,
    "email"          varchar(254)             NOT NULL,
    "is_staff"       boolean                  NOT NULL,
    "is_active"      boolean                  NOT NULL,
    "date_joined"    timestamp with time zone NOT NULL
);
--
-- Create proxy model GroupPermissions
--
--
-- Create proxy model GroupProxy
--
--
-- Create proxy model PermissionProxy
--
--
-- Create proxy model UserGroups
--
--
-- Create proxy model UserPermissions
--
--
-- Create proxy model UserProfileBarMembership
--
--
-- Create proxy model UserProxy
--
--
-- Create trigger snapshot_insert on model userprofile
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_31610()
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
                                          "email_confirmed", "employer", "id",
                                          "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "plaintext_preferred", "recap_email", "state",
                                          "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe",
            NEW."avatar", NEW."city", NEW."email_confirmed", NEW."employer", NEW."id",
            NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email",
            NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts",
            NEW."user_id", NEW."wants_newsletter", NEW."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_31610 ON "users_userprofile";
CREATE TRIGGER pgtrigger_snapshot_insert_31610
    AFTER INSERT
    ON "users_userprofile"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_31610();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_31610 ON "users_userprofile" IS 'aa341719534a80b6c9f390387615a65236106919';
;
--
-- Create trigger snapshot_update on model userprofile
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_74231()
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
                                          "email_confirmed", "employer", "id",
                                          "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "plaintext_preferred", "recap_email", "state",
                                          "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe",
            NEW."avatar", NEW."city", NEW."email_confirmed", NEW."employer", NEW."id",
            NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email",
            NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts",
            NEW."user_id", NEW."wants_newsletter", NEW."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_74231 ON "users_userprofile";
CREATE TRIGGER pgtrigger_snapshot_update_74231
    AFTER UPDATE
    ON "users_userprofile"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_74231();

COMMENT ON TRIGGER pgtrigger_snapshot_update_74231 ON "users_userprofile" IS '5a100c4fbaec17c304654aaeca224fdd740ead43';
;
--
-- Add field pgh_context to userproxyevent
--
ALTER TABLE "users_userproxyevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to userproxyevent
--
ALTER TABLE "users_userproxyevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field pgh_context to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field barmembership to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "barmembership_id" integer NOT NULL;
--
-- Add field pgh_context to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field userprofile to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "userprofile_id" integer NOT NULL;
--
-- Add field permission to userpermissionsevent
--
ALTER TABLE "users_userpermissionsevent"
    ADD COLUMN "permission_id" integer NOT NULL;
--
-- Add field pgh_context to userpermissionsevent
--
ALTER TABLE "users_userpermissionsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field user to userpermissionsevent
--
ALTER TABLE "users_userpermissionsevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field group to usergroupsevent
--
ALTER TABLE "users_usergroupsevent"
    ADD COLUMN "group_id" integer NOT NULL;
--
-- Add field pgh_context to usergroupsevent
--
ALTER TABLE "users_usergroupsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field user to usergroupsevent
--
ALTER TABLE "users_usergroupsevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field content_type to permissionproxyevent
--
ALTER TABLE "users_permissionproxyevent"
    ADD COLUMN "content_type_id" integer NOT NULL;
--
-- Add field pgh_context to permissionproxyevent
--
ALTER TABLE "users_permissionproxyevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to permissionproxyevent
--
ALTER TABLE "users_permissionproxyevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field pgh_context to groupproxyevent
--
ALTER TABLE "users_groupproxyevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to groupproxyevent
--
ALTER TABLE "users_groupproxyevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field group to grouppermissionsevent
--
ALTER TABLE "users_grouppermissionsevent"
    ADD COLUMN "group_id" integer NOT NULL;
--
-- Add field permission to grouppermissionsevent
--
ALTER TABLE "users_grouppermissionsevent"
    ADD COLUMN "permission_id" integer NOT NULL;
--
-- Add field pgh_context to grouppermissionsevent
--
ALTER TABLE "users_grouppermissionsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Create trigger snapshot_insert on model grouppermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_47043()
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
    INSERT INTO "users_grouppermissionsevent" ("group_id", "id", "permission_id",
                                               "pgh_context_id", "pgh_created_at",
                                               "pgh_label")
    VALUES (NEW."group_id", NEW."id", NEW."permission_id", _pgh_attach_context(), NOW(),
            'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_47043 ON "auth_group_permissions";
CREATE TRIGGER pgtrigger_snapshot_insert_47043
    AFTER INSERT
    ON "auth_group_permissions"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_47043();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_47043 ON "auth_group_permissions" IS '190fc4d33be33806907c415607dd61c4aa035efb';
;
--
-- Create trigger snapshot_update on model grouppermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8e426()
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
    INSERT INTO "users_grouppermissionsevent" ("group_id", "id", "permission_id",
                                               "pgh_context_id", "pgh_created_at",
                                               "pgh_label")
    VALUES (NEW."group_id", NEW."id", NEW."permission_id", _pgh_attach_context(), NOW(),
            'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8e426 ON "auth_group_permissions";
CREATE TRIGGER pgtrigger_snapshot_update_8e426
    AFTER UPDATE
    ON "auth_group_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_8e426();

COMMENT ON TRIGGER pgtrigger_snapshot_update_8e426 ON "auth_group_permissions" IS '76526fcb4e1e199175ecfc8b75cda40c2d740a12';
;
--
-- Create trigger snapshot_insert on model groupproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_0bb2c()
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
    INSERT INTO "users_groupproxyevent" ("id", "name", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (NEW."id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0bb2c ON "auth_group";
CREATE TRIGGER pgtrigger_snapshot_insert_0bb2c
    AFTER INSERT
    ON "auth_group"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_0bb2c();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_0bb2c ON "auth_group" IS 'ad0c3757ff07badb1e01dc4d277b1072b4b2537c';
;
--
-- Create trigger snapshot_update on model groupproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_1e0d3()
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
    INSERT INTO "users_groupproxyevent" ("id", "name", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (NEW."id", NEW."name", _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1e0d3 ON "auth_group";
CREATE TRIGGER pgtrigger_snapshot_update_1e0d3
    AFTER UPDATE
    ON "auth_group"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_1e0d3();

COMMENT ON TRIGGER pgtrigger_snapshot_update_1e0d3 ON "auth_group" IS '2719a239ac1a52026c65d804131c59ed0f3417b6';
;
--
-- Create trigger snapshot_insert on model permissionproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_c294b()
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
    INSERT INTO "users_permissionproxyevent" ("codename", "content_type_id", "id",
                                              "name", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "pgh_obj_id")
    VALUES (NEW."codename", NEW."content_type_id", NEW."id", NEW."name",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_c294b ON "auth_permission";
CREATE TRIGGER pgtrigger_snapshot_insert_c294b
    AFTER INSERT
    ON "auth_permission"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_c294b();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_c294b ON "auth_permission" IS 'ce59d3bcfa5af69fa46bf960f1bb31d8cf32dfed';
;
--
-- Create trigger snapshot_update on model permissionproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8f943()
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
    INSERT INTO "users_permissionproxyevent" ("codename", "content_type_id", "id",
                                              "name", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "pgh_obj_id")
    VALUES (NEW."codename", NEW."content_type_id", NEW."id", NEW."name",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f943 ON "auth_permission";
CREATE TRIGGER pgtrigger_snapshot_update_8f943
    AFTER UPDATE
    ON "auth_permission"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_8f943();

COMMENT ON TRIGGER pgtrigger_snapshot_update_8f943 ON "auth_permission" IS 'c10177884052b7fc204de8efe6d380da632dd530';
;
--
-- Create trigger snapshot_insert on model usergroups
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_cb58e()
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
    INSERT INTO "users_usergroupsevent" ("group_id", "id", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "user_id")
    VALUES (NEW."group_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cb58e ON "auth_user_groups";
CREATE TRIGGER pgtrigger_snapshot_insert_cb58e
    AFTER INSERT
    ON "auth_user_groups"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_cb58e();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_cb58e ON "auth_user_groups" IS '07f96f95d10ebed7e9e1997396c923e1de1fa62c';
;
--
-- Create trigger snapshot_update on model usergroups
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_591a4()
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
    INSERT INTO "users_usergroupsevent" ("group_id", "id", "pgh_context_id",
                                         "pgh_created_at", "pgh_label", "user_id")
    VALUES (NEW."group_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_591a4 ON "auth_user_groups";
CREATE TRIGGER pgtrigger_snapshot_update_591a4
    AFTER UPDATE
    ON "auth_user_groups"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_591a4();

COMMENT ON TRIGGER pgtrigger_snapshot_update_591a4 ON "auth_user_groups" IS 'f63dc20f489b3da60b0b4fd7375f7dc75acbb328';
;
--
-- Create trigger snapshot_insert on model userpermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_46522()
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
    VALUES (NEW."id", NEW."permission_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_46522 ON "auth_user_user_permissions";
CREATE TRIGGER pgtrigger_snapshot_insert_46522
    AFTER INSERT
    ON "auth_user_user_permissions"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_46522();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_46522 ON "auth_user_user_permissions" IS '64d04f34bf969cb0915906dd0745633c03247e7e';
;
--
-- Create trigger snapshot_update on model userpermissions
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_80307()
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
    VALUES (NEW."id", NEW."permission_id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."user_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_80307 ON "auth_user_user_permissions";
CREATE TRIGGER pgtrigger_snapshot_update_80307
    AFTER UPDATE
    ON "auth_user_user_permissions"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_80307();

COMMENT ON TRIGGER pgtrigger_snapshot_update_80307 ON "auth_user_user_permissions" IS 'b311129b652886b174cd1dbbd9f3347a49cad778';
;
--
-- Create trigger snapshot_insert on model userprofilebarmembership
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_de1c8()
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
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (NEW."barmembership_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_de1c8 ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_snapshot_insert_de1c8
    AFTER INSERT
    ON "users_userprofile_barmembership"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_de1c8();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_de1c8 ON "users_userprofile_barmembership" IS '2af83be1b83550629a688c44113e1c0430d8ef8e';
;
--
-- Create trigger snapshot_update on model userprofilebarmembership
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cb3f2()
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
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (NEW."barmembership_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cb3f2 ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_snapshot_update_cb3f2
    AFTER UPDATE
    ON "users_userprofile_barmembership"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cb3f2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cb3f2 ON "users_userprofile_barmembership" IS 'dfa53db455704cc58ca39636c262a174fe876878';
;
--
-- Create trigger snapshot_insert on model userproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_70025()
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
    INSERT INTO "users_userproxyevent" ("date_joined", "email", "first_name", "id",
                                        "is_active", "is_staff", "is_superuser",
                                        "last_login", "last_name", "password",
                                        "pgh_context_id", "pgh_created_at", "pgh_label",
                                        "pgh_obj_id", "username")
    VALUES (NEW."date_joined", NEW."email", NEW."first_name", NEW."id", NEW."is_active",
            NEW."is_staff", NEW."is_superuser", NEW."last_login", NEW."last_name",
            NEW."password", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."username");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_70025 ON "auth_user";
CREATE TRIGGER pgtrigger_snapshot_insert_70025
    AFTER INSERT
    ON "auth_user"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_70025();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_70025 ON "auth_user" IS 'c66c0d34ec5bfdb1c02556c8d346afb57abe0e9b';
;
--
-- Create trigger snapshot_update on model userproxy
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_b6e18()
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
    INSERT INTO "users_userproxyevent" ("date_joined", "email", "first_name", "id",
                                        "is_active", "is_staff", "is_superuser",
                                        "last_login", "last_name", "password",
                                        "pgh_context_id", "pgh_created_at", "pgh_label",
                                        "pgh_obj_id", "username")
    VALUES (NEW."date_joined", NEW."email", NEW."first_name", NEW."id", NEW."is_active",
            NEW."is_staff", NEW."is_superuser", NEW."last_login", NEW."last_name",
            NEW."password", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."username");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_b6e18 ON "auth_user";
CREATE TRIGGER pgtrigger_snapshot_update_b6e18
    AFTER UPDATE
    ON "auth_user"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_b6e18();

COMMENT ON TRIGGER pgtrigger_snapshot_update_b6e18 ON "auth_user" IS 'd90516903b3ce015d76bb46097f69a802f0f7666';
;
CREATE INDEX "users_userproxyevent_pgh_context_id_ca6e4843" ON "users_userproxyevent" ("pgh_context_id");
CREATE INDEX "users_userproxyevent_pgh_obj_id_050f8258" ON "users_userproxyevent" ("pgh_obj_id");
CREATE INDEX "users_userprofileevent_pgh_context_id_b240d6a7" ON "users_userprofileevent" ("pgh_context_id");
CREATE INDEX "users_userprofileevent_pgh_obj_id_d6261087" ON "users_userprofileevent" ("pgh_obj_id");
CREATE INDEX "users_userprofileevent_user_id_52cc3748" ON "users_userprofileevent" ("user_id");
CREATE INDEX "users_userprofilebarmembershipevent_barmembership_id_90427e0c" ON "users_userprofilebarmembershipevent" ("barmembership_id");
CREATE INDEX "users_userprofilebarmembershipevent_pgh_context_id_fee0358d" ON "users_userprofilebarmembershipevent" ("pgh_context_id");
CREATE INDEX "users_userprofilebarmembershipevent_userprofile_id_b75055e4" ON "users_userprofilebarmembershipevent" ("userprofile_id");
CREATE INDEX "users_userpermissionsevent_permission_id_eb7f72ee" ON "users_userpermissionsevent" ("permission_id");
CREATE INDEX "users_userpermissionsevent_pgh_context_id_b3efbbd0" ON "users_userpermissionsevent" ("pgh_context_id");
CREATE INDEX "users_userpermissionsevent_user_id_e8fc030a" ON "users_userpermissionsevent" ("user_id");
CREATE INDEX "users_usergroupsevent_group_id_3c61f74f" ON "users_usergroupsevent" ("group_id");
CREATE INDEX "users_usergroupsevent_pgh_context_id_bfcc7289" ON "users_usergroupsevent" ("pgh_context_id");
CREATE INDEX "users_usergroupsevent_user_id_e2425193" ON "users_usergroupsevent" ("user_id");
CREATE INDEX "users_permissionproxyevent_content_type_id_0c5c8281" ON "users_permissionproxyevent" ("content_type_id");
CREATE INDEX "users_permissionproxyevent_pgh_context_id_4247b7af" ON "users_permissionproxyevent" ("pgh_context_id");
CREATE INDEX "users_permissionproxyevent_pgh_obj_id_9295ce47" ON "users_permissionproxyevent" ("pgh_obj_id");
CREATE INDEX "users_groupproxyevent_pgh_context_id_5010dd15" ON "users_groupproxyevent" ("pgh_context_id");
CREATE INDEX "users_groupproxyevent_pgh_obj_id_d5294d03" ON "users_groupproxyevent" ("pgh_obj_id");
CREATE INDEX "users_grouppermissionsevent_group_id_5915b9ab" ON "users_grouppermissionsevent" ("group_id");
CREATE INDEX "users_grouppermissionsevent_permission_id_193b4ac1" ON "users_grouppermissionsevent" ("permission_id");
CREATE INDEX "users_grouppermissionsevent_pgh_context_id_42477fa8" ON "users_grouppermissionsevent" ("pgh_context_id");
COMMIT;
